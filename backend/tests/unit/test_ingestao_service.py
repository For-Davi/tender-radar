"""Testes do caso de uso de ingestão, com fakes em memória (sem rede, sem banco)."""

from datetime import UTC, date, datetime

import pytest

from radar.ports.contratacoes_source import RawItem
from radar.services.ingestao import (
    IngestaoService,
    JanelaIngestao,
    detect_file_type,
    payload_hash,
)
from tests.fakes import (
    FakePublisher,
    FakeSource,
    InMemoryBronze,
    InMemoryStorage,
    make_edital,
    make_raw,
)

NOW = datetime(2025, 9, 1, 12, 0, tzinfo=UTC)
JANELA = JanelaIngestao(date(2025, 9, 1), date(2025, 9, 1), modalidades=(6,), ufs=("CE",))


class Env:
    """Monta o serviço com fakes e deixa tudo acessível para as asserções."""

    def __init__(self) -> None:
        self.source = FakeSource()
        self.bronze = InMemoryBronze()
        self.storage = InMemoryStorage()
        self.publisher = FakePublisher()
        self.service = IngestaoService(
            self.source, self.bronze, self.storage, self.publisher, clock=lambda: NOW
        )

    def add(self, sequencial: int, *, documentos: bool = True, **payload: object) -> str:
        raw = make_raw(sequencial, **payload)
        numero = raw.ref.numero_controle_pncp
        self.source.contratacoes.setdefault((6, "CE"), []).append(raw)
        self.source.itens[numero] = [
            RawItem(1, True, {"numeroItem": 1}),
            RawItem(2, False, {"numeroItem": 2}),
        ]
        self.source.resultados[(numero, 1)] = [{"niFornecedor": "12561319000175"}]
        if documentos:
            self.source.documentos[numero] = [make_edital(1)]
        return numero


@pytest.fixture
def env() -> Env:
    return Env()


# ------------------------------------------------------------------ fluxo completo


def test_full_flow_bronze_document_and_event(env: Env) -> None:
    numero = env.add(1)

    report = env.service.run(JANELA)

    (record,) = env.bronze.versions
    assert record.numero_controle_pncp == numero
    assert record.coletado_em == NOW
    assert set(record.payload) == {"contratacao", "itens", "resultados", "arquivos"}
    assert record.payload["resultados"] == {"1": [{"niFornecedor": "12561319000175"}]}
    assert env.storage.files == {"11222333000181/2025/1/1.pdf": b"%PDF-1.7 edital de teste"}
    (event,) = env.publisher.events
    assert event.numero_controle_pncp == numero
    assert event.caminho == "11222333000181/2025/1/1.pdf"
    assert env.bronze.pending_documents() == []
    assert report.contratacoes_lidas == 1
    assert report.versoes_novas == 1
    assert report.documentos_baixados == 1
    assert report.eventos_publicados == 1
    assert report.falhas == []


def test_results_are_fetched_only_for_items_with_result(env: Env) -> None:
    numero = env.add(1)
    env.source.resultados[(numero, 2)] = [{"nao": "deveria ser buscado"}]

    env.service.run(JANELA)

    assert list(env.bronze.versions[0].payload["resultados"]) == ["1"]


def test_iterates_all_modalidades_and_ufs(env: Env) -> None:
    env.add(1)
    env.source.contratacoes[(8, "SP")] = [make_raw(2)]

    report = env.service.run(
        JanelaIngestao(date(2025, 9, 1), date(2025, 9, 1), modalidades=(6, 8), ufs=("CE", "SP"))
    )

    assert report.contratacoes_lidas == 2


# ------------------------------------------------------------------ idempotência


def test_running_twice_gives_same_state(env: Env) -> None:
    env.add(1)
    env.add(2)

    env.service.run(JANELA)
    second = env.service.run(JANELA)

    assert len(env.bronze.versions) == 2
    assert len(env.storage.files) == 2
    assert len(env.publisher.events) == 2  # nenhum evento repetido
    assert second.versoes_novas == 0
    assert second.inalteradas == 2
    assert second.documentos_baixados == 0
    assert second.eventos_publicados == 0
    assert len(env.source.downloads) == 2  # nem baixou de novo


def test_changed_payload_creates_new_version_but_no_new_event(env: Env) -> None:
    env.add(1)
    env.service.run(JANELA)

    env.source.contratacoes[(6, "CE")] = [make_raw(1, objetoCompra="Objeto retificado")]
    report = env.service.run(JANELA)

    assert report.versoes_novas == 1
    assert len(env.bronze.versions) == 2
    assert len(env.publisher.events) == 1  # o edital é o mesmo: não republica


# ------------------------------------------------------------------ falhas isoladas


def test_pdf_download_failure_does_not_stop_batch(env: Env) -> None:
    env.add(1)
    env.add(2)
    env.source.fail_download_for.add("https://pncp.test/doc/1")
    env.source.documentos[make_raw(2).ref.numero_controle_pncp] = [make_edital(2)]

    report = env.service.run(JANELA)

    assert report.contratacoes_lidas == 2
    assert report.versoes_novas == 2  # o bruto das duas foi salvo
    assert report.documentos_baixados == 1
    assert len(report.falhas) == 1
    assert "doc/1" in report.falhas[0]


def test_failed_download_is_retried_on_next_run(env: Env) -> None:
    env.add(1)
    env.source.fail_download_for.add("https://pncp.test/doc/1")
    env.service.run(JANELA)

    env.source.fail_download_for.clear()
    report = env.service.run(JANELA)

    assert report.documentos_baixados == 1
    assert len(env.publisher.events) == 1


def test_details_failure_skips_only_that_contratacao(env: Env) -> None:
    bad = env.add(1)
    env.add(2)
    env.source.fail_details_for.add(bad)

    report = env.service.run(JANELA)

    assert [v.numero_controle_pncp for v in env.bronze.versions] == [
        make_raw(2).ref.numero_controle_pncp
    ]
    assert report.contratacoes_lidas == 2
    assert len(report.falhas) == 1
    assert bad in report.falhas[0]


def test_listing_failure_skips_only_that_modalidade_uf(env: Env) -> None:
    env.add(1)
    env.source.fail_listing.add((8, "CE"))

    report = env.service.run(
        JanelaIngestao(date(2025, 9, 1), date(2025, 9, 1), modalidades=(8, 6), ufs=("CE",))
    )

    assert report.versoes_novas == 1
    assert len(report.falhas) == 1
    assert "8/CE" in report.falhas[0]


def test_storage_failure_is_reported_and_not_registered(env: Env) -> None:
    env.add(1)
    env.storage.fail = True

    report = env.service.run(JANELA)

    assert report.documentos_baixados == 0
    assert env.bronze.documents == {}  # sem registro: tenta de novo na próxima execução
    assert len(report.falhas) == 1


# ------------------------------------------------------------------ outbox


def test_publish_failure_keeps_document_pending_and_retries_next_run(env: Env) -> None:
    env.add(1)
    env.publisher.failures_left = 1

    first = env.service.run(JANELA)

    assert first.eventos_publicados == 0
    assert len(env.bronze.pending_documents()) == 1
    assert len(first.falhas) == 1

    second = env.service.run(JANELA)

    assert second.eventos_publicados == 1
    assert env.bronze.pending_documents() == []
    assert len(env.source.downloads) == 1  # não baixou de novo: só republicou


def test_publish_failure_stops_publishing_remaining(env: Env) -> None:
    # se o broker caiu, não adianta tentar os próximos agora: ficam para a próxima execução
    env.add(1)
    env.add(2)
    env.publisher.failures_left = 1

    report = env.service.run(JANELA)

    assert report.eventos_publicados == 0
    assert len(env.bronze.pending_documents()) == 2


# ------------------------------------------------------------------ documentos


def test_only_edital_documents_are_downloaded(env: Env) -> None:
    numero = env.add(1, documentos=False)
    env.source.documentos[numero] = [make_edital(1, eh_edital=False), make_edital(2)]

    env.service.run(JANELA)

    assert env.source.downloads == ["https://pncp.test/doc/2"]
    assert len(env.bronze.versions[0].payload["arquivos"]) == 2  # bronze guarda a lista toda


def test_zip_document_keeps_extension(env: Env) -> None:
    env.add(1)
    env.source.arquivos["https://pncp.test/doc/1"] = b"PK\x03\x04conteudo"

    env.service.run(JANELA)

    assert list(env.storage.files) == ["11222333000181/2025/1/1.zip"]
    assert env.bronze.documents[(make_raw(1).ref.numero_controle_pncp, 1)].tipo_arquivo == "zip"


# ------------------------------------------------------------------ funções puras


def test_payload_hash_ignores_key_order() -> None:
    assert payload_hash({"a": 1, "b": [1, 2]}) == payload_hash({"b": [1, 2], "a": 1})
    assert payload_hash({"a": 1}) != payload_hash({"a": 2})


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (b"%PDF-1.4 ...", "pdf"),
        (b"PK\x03\x04...", "zip"),
        (b"<html>", "desconhecido"),
        (b"", "desconhecido"),
    ],
)
def test_detect_file_type(content: bytes, expected: str) -> None:
    assert detect_file_type(content) == expected


def test_event_is_published_as_soon_as_document_is_stored(env: Env) -> None:
    """Regressão (achada na execução real): o evento só saía no fim da execução.

    Com o PNCP lento, uma execução leva dezenas de minutos, e os editais já baixados
    ficavam parados esperando. O evento do 1º edital deve sair antes do 2º download.
    """
    env.add(1)
    env.add(2)
    env.source.documentos[make_raw(2).ref.numero_controle_pncp] = [make_edital(2)]
    events_at_download: list[int] = []
    original_download = env.source.download

    def spying_download(url: str) -> bytes:
        events_at_download.append(len(env.publisher.events))
        return original_download(url)

    env.source.download = spying_download  # type: ignore[method-assign]

    env.service.run(JANELA)

    assert events_at_download == [0, 1]  # no 2º download, o 1º evento já tinha saído


def test_pending_from_previous_run_is_published_at_start(env: Env) -> None:
    env.add(1)
    env.publisher.failures_left = 1
    env.service.run(JANELA)  # broker fora: documento fica pendente
    env.source.contratacoes.clear()  # na próxima execução, nada novo no PNCP

    report = env.service.run(JANELA)

    assert report.eventos_publicados == 1
    assert env.bronze.pending_documents() == []
