"""Pipeline bronze -> silver com fakes em memória: lote, rejeições, marca d'água."""

import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from radar.pipelines.bronze_to_silver import PIPELINE, BronzeToSilverPipeline
from radar.ports.bronze import BronzeVersion
from radar.ports.silver import MotivoRejeicao
from tests.bronze_payloads import make_version, payload_with_numero
from tests.fakes import FakeSilverUnitOfWork, InMemoryBronzeReader

NOW = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)
LAG = timedelta(minutes=1)


class Clock:
    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def _version(sequencial: int, minutes_ago: int = 30, **contratacao: object) -> BronzeVersion:
    payload = payload_with_numero(sequencial)
    payload["contratacao"] |= contratacao
    return make_version(payload, vigente_desde=NOW - timedelta(minutes=minutes_ago))


def _numero(sequencial: int) -> str:
    return f"07954480000179-1-{sequencial:06d}/2025"


@pytest.fixture
def bronze() -> InMemoryBronzeReader:
    return InMemoryBronzeReader()


@pytest.fixture
def silver() -> FakeSilverUnitOfWork:
    return FakeSilverUnitOfWork()


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def make_pipeline(
    bronze: InMemoryBronzeReader, silver: FakeSilverUnitOfWork, clock: Clock
) -> Callable[..., BronzeToSilverPipeline]:
    def factory(
        tamanho_lote: int = 100, monotonic: Callable[[], float] = time.monotonic
    ) -> BronzeToSilverPipeline:
        return BronzeToSilverPipeline(
            bronze,
            silver,
            tamanho_lote=tamanho_lote,
            atraso_seguranca=LAG,
            clock=clock,
            monotonic=monotonic,
        )

    return factory


# ------------------------------------------------------------------ gravação e contagens


def test_valid_versions_are_saved_and_committed(
    bronze: InMemoryBronzeReader,
    silver: FakeSilverUnitOfWork,
    make_pipeline: Callable[..., BronzeToSilverPipeline],
) -> None:
    bronze.versions = [_version(1), _version(2)]

    report = make_pipeline().run()

    assert (report.lidas, report.gravadas, report.rejeitadas) == (2, 2, 0)
    assert report.itens_gravados == 6  # 3 itens por contratação na fixture
    assert set(silver.committed.contratacoes) == {_numero(1), _numero(2)}
    assert len(silver.committed.orgaos) == 1  # mesmo órgão nas duas
    assert len(silver.committed.fornecedores) == 1
    assert silver.committed.marcas[PIPELINE] == NOW - LAG


def test_invalid_record_is_rejected_with_reason_and_batch_continues(
    bronze: InMemoryBronzeReader,
    silver: FakeSilverUnitOfWork,
    make_pipeline: Callable[..., BronzeToSilverPipeline],
) -> None:
    ruim = _version(2, minutes_ago=20, dataPublicacaoPncp="ontem")
    bronze.versions = [_version(1, minutes_ago=30), ruim, _version(3, minutes_ago=10)]

    report = make_pipeline().run()

    assert (report.lidas, report.gravadas, report.rejeitadas) == (3, 2, 1)
    assert set(silver.committed.contratacoes) == {_numero(1), _numero(3)}
    (rejeicao,) = silver.committed.rejeicoes.values()
    assert rejeicao.numero_controle_pncp == _numero(2)
    assert rejeicao.bronze_hash == ruim.hash
    assert rejeicao.motivo is MotivoRejeicao.CAMPO_INVALIDO


def test_item_rejections_are_recorded_and_counted(
    bronze: InMemoryBronzeReader,
    silver: FakeSilverUnitOfWork,
    make_pipeline: Callable[..., BronzeToSilverPipeline],
) -> None:
    version = _version(1)
    version.payload["itens"][0]["quantidade"] = 0
    bronze.versions = [make_version(version.payload, vigente_desde=version.vigente_desde)]

    report = make_pipeline().run()

    assert (report.gravadas, report.itens_gravados, report.itens_rejeitados) == (1, 2, 1)
    (rejeicao,) = silver.committed.rejeicoes.values()
    assert rejeicao.numero_item == 1
    assert rejeicao.motivo is MotivoRejeicao.REGRA_NEGOCIO


def test_inconsistent_totals_are_counted(
    bronze: InMemoryBronzeReader, make_pipeline: Callable[..., BronzeToSilverPipeline]
) -> None:
    bronze.versions = [_version(1, valorTotalEstimado=10.0), _version(2)]

    report = make_pipeline().run()

    assert report.inconsistentes == 1
    assert report.gravadas == 2


def test_database_refusal_becomes_persistence_rejection(
    bronze: InMemoryBronzeReader,
    silver: FakeSilverUnitOfWork,
    make_pipeline: Callable[..., BronzeToSilverPipeline],
) -> None:
    bronze.versions = [_version(1), _version(2, minutes_ago=10)]
    silver.contratacoes.fail_for = {_numero(1)}

    report = make_pipeline().run()

    assert (report.gravadas, report.rejeitadas) == (1, 1)
    (rejeicao,) = silver.committed.rejeicoes.values()
    assert rejeicao.motivo is MotivoRejeicao.PERSISTENCIA
    assert set(silver.committed.contratacoes) == {_numero(2)}


def test_report_has_duration(
    bronze: InMemoryBronzeReader, make_pipeline: Callable[..., BronzeToSilverPipeline]
) -> None:
    ticks = iter([100.0, 102.5])

    report = make_pipeline(monotonic=lambda: next(ticks)).run()

    assert report.duracao_segundos == 2.5


# ------------------------------------------------------------------ incremental


def test_second_run_processes_nothing_new(
    bronze: InMemoryBronzeReader, clock: Clock, make_pipeline: Callable[..., BronzeToSilverPipeline]
) -> None:
    bronze.versions = [_version(1), _version(2)]
    make_pipeline().run()
    clock.now = NOW + timedelta(hours=1)

    report = make_pipeline().run()

    assert report.lidas == 0
    # a 2ª execução começa exatamente onde a 1ª terminou
    assert bronze.calls[1] == (NOW - LAG, clock.now - LAG)


def test_only_versions_newer_than_watermark_are_processed(
    bronze: InMemoryBronzeReader,
    silver: FakeSilverUnitOfWork,
    clock: Clock,
    make_pipeline: Callable[..., BronzeToSilverPipeline],
) -> None:
    bronze.versions = [_version(1), _version(2)]
    make_pipeline().run()
    # nova versão da contratação 1 (objeto mudou), coletada depois da 1ª execução
    nova = payload_with_numero(1)
    nova["contratacao"]["objetoCompra"] = "Objeto retificado"
    bronze.versions.append(make_version(nova, vigente_desde=NOW + timedelta(minutes=5)))
    clock.now = NOW + timedelta(hours=1)

    report = make_pipeline().run()

    assert (report.lidas, report.gravadas) == (1, 1)
    assert silver.committed.contratacoes[_numero(1)].objeto == "Objeto retificado"


def test_very_recent_versions_wait_for_the_next_run(
    bronze: InMemoryBronzeReader, clock: Clock, make_pipeline: Callable[..., BronzeToSilverPipeline]
) -> None:
    # gravada há 10 s: pode haver outra gravação "atrasada" com horário anterior ainda
    # chegando; o pipeline só lê até agora - atraso de segurança
    bronze.versions = [
        make_version(payload_with_numero(1), vigente_desde=NOW - timedelta(seconds=10))
    ]

    first = make_pipeline().run()
    clock.now = NOW + timedelta(minutes=5)
    second = make_pipeline().run()

    assert (first.lidas, second.lidas) == (0, 1)


def test_full_run_reprocesses_everything_without_duplicating(
    bronze: InMemoryBronzeReader,
    silver: FakeSilverUnitOfWork,
    make_pipeline: Callable[..., BronzeToSilverPipeline],
) -> None:
    bronze.versions = [_version(1), _version(2, dataPublicacaoPncp="ontem")]
    make_pipeline().run()

    report = make_pipeline().run(completo=True)

    assert report.lidas == 2
    assert bronze.calls[1][0] is None  # sem marca: desde o início
    assert len(silver.committed.contratacoes) == 1
    assert len(silver.committed.rejeicoes) == 1  # a mesma rejeição não duplica


# ------------------------------------------------------------------ falhas e transação


def test_unexpected_error_rolls_back_and_keeps_watermark(
    bronze: InMemoryBronzeReader,
    silver: FakeSilverUnitOfWork,
    make_pipeline: Callable[..., BronzeToSilverPipeline],
) -> None:
    bronze.versions = [_version(1, minutes_ago=30), _version(2, minutes_ago=20)]
    silver.crash_on = _numero(2)

    with pytest.raises(RuntimeError, match="banco"):
        make_pipeline().run()

    assert silver.rollbacks == 1
    assert PIPELINE not in silver.committed.marcas  # nada avançou
    assert silver.committed.contratacoes == {}

    silver.crash_on = None
    report = make_pipeline().run()  # a próxima execução refaz tudo

    assert report.gravadas == 2


def test_commits_in_batches_but_watermark_only_at_the_end(
    bronze: InMemoryBronzeReader,
    silver: FakeSilverUnitOfWork,
    make_pipeline: Callable[..., BronzeToSilverPipeline],
) -> None:
    bronze.versions = [_version(n, minutes_ago=60 - n) for n in range(1, 6)]
    silver.crash_on = _numero(5)

    with pytest.raises(RuntimeError):
        make_pipeline(tamanho_lote=2).run()

    # lotes 1-2 e 3-4 ficaram gravados (progresso não se perde)...
    assert set(silver.committed.contratacoes) == {_numero(n) for n in range(1, 5)}
    # ...mas a marca não avançou: a próxima execução relê tudo (upsert = sem duplicar)
    assert PIPELINE not in silver.committed.marcas


def test_batch_commit_count(
    bronze: InMemoryBronzeReader,
    silver: FakeSilverUnitOfWork,
    make_pipeline: Callable[..., BronzeToSilverPipeline],
) -> None:
    bronze.versions = [_version(n, minutes_ago=60 - n) for n in range(1, 6)]

    make_pipeline(tamanho_lote=2).run()

    assert silver.commits == 3  # após 2, após 4 e o final (com a marca)
