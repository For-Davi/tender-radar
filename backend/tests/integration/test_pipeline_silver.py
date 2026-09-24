"""Bronze no MongoDB real -> pipeline -> silver no Postgres real: as contagens batem."""

import copy
from datetime import UTC, datetime, timedelta

import pytest
from pymongo.database import Database
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from radar.adapters.mongo.bronze import MongoBronzeRepository, MongoDoc
from radar.adapters.postgres.models import (
    ContratacaoModel,
    FornecedorModel,
    ItemContratacaoModel,
    OrgaoModel,
    RegistroRejeitadoModel,
)
from radar.adapters.postgres.silver import SqlSilverUnitOfWork
from radar.pipelines.bronze_to_silver import PIPELINE, BronzeToSilverPipeline, RelatorioPipeline
from radar.ports.bronze import BronzeRecord
from radar.ports.contratacoes_source import JsonDict
from radar.ports.silver import MotivoRejeicao, Problema, Rejeicao
from radar.services.ingestao import payload_hash
from tests.bronze_payloads import payload_with_numero

T0 = datetime(2026, 9, 24, 8, 0, tzinfo=UTC)


@pytest.fixture
def bronze(mongo_db: Database[MongoDoc]) -> MongoBronzeRepository:
    repository = MongoBronzeRepository(mongo_db)
    repository.ensure_indexes()
    return repository


def _save(bronze: MongoBronzeRepository, payload: JsonDict, when: datetime) -> None:
    numero = payload["contratacao"]["numeroControlePNCP"]
    bronze.save_if_changed(BronzeRecord(numero, payload, payload_hash(payload), when))


def _run(
    bronze: MongoBronzeRepository, session: Session, now: datetime, *, completo: bool = False
) -> RelatorioPipeline:
    pipeline = BronzeToSilverPipeline(
        bronze, SqlSilverUnitOfWork(session), tamanho_lote=2, clock=lambda: now
    )
    return pipeline.run(completo=completo)


def _count(session: Session, model: type) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def _seed(bronze: MongoBronzeRepository) -> None:
    """3 contratações válidas, 1 com data inválida, 1 com um item de quantidade 0."""
    for sequencial in (1, 2, 3):
        _save(bronze, payload_with_numero(sequencial), T0 + timedelta(minutes=sequencial))
    data_ruim = payload_with_numero(4)
    data_ruim["contratacao"]["dataPublicacaoPncp"] = "30/02/2025"
    _save(bronze, data_ruim, T0 + timedelta(minutes=4))
    item_ruim = payload_with_numero(5)
    item_ruim["itens"][1]["quantidade"] = 0
    _save(bronze, item_ruim, T0 + timedelta(minutes=5))


def test_bronze_to_silver_counts_match(bronze: MongoBronzeRepository, session: Session) -> None:
    _seed(bronze)

    report = _run(bronze, session, T0 + timedelta(hours=1))

    assert (report.lidas, report.gravadas, report.rejeitadas) == (5, 4, 1)
    assert (report.itens_gravados, report.itens_rejeitados) == (11, 1)
    assert _count(session, ContratacaoModel) == 4
    assert _count(session, ItemContratacaoModel) == 3 * 3 + 2
    assert _count(session, OrgaoModel) == 1
    assert _count(session, FornecedorModel) == 1
    motivos = session.execute(
        select(RegistroRejeitadoModel.numero_item, RegistroRejeitadoModel.motivo).order_by(
            RegistroRejeitadoModel.numero_item.nulls_first()
        )
    ).all()
    assert [tuple(row) for row in motivos] == [(None, "campo_invalido"), (2, "regra_negocio")]


def test_rejection_details_are_queryable_json(
    bronze: MongoBronzeRepository, session: Session
) -> None:
    _seed(bronze)
    _run(bronze, session, T0 + timedelta(hours=1))

    # JSONB: dá para consultar dentro do JSON com os operadores do Postgres
    campo = session.scalar(
        text(
            "SELECT detalhes -> 0 ->> 'campo' FROM silver.registros_rejeitados "
            "WHERE numero_item IS NULL"
        )
    )
    assert campo == "contratacao.dataPublicacaoPncp"


def test_values_are_exact_and_dates_have_timezone(
    bronze: MongoBronzeRepository, session: Session
) -> None:
    _save(bronze, payload_with_numero(1), T0)
    _run(bronze, session, T0 + timedelta(hours=1))

    contratacao = session.scalars(select(ContratacaoModel)).one()
    # float JSON 5367337.33 guardado exato em numeric(18,4)
    assert str(contratacao.valor_total_estimado) == "5367337.3300"
    # "2025-03-10T07:15:44" (Brasília) = 10:15:44 UTC
    assert contratacao.data_publicacao == datetime(2025, 3, 10, 10, 15, 44, tzinfo=UTC)


def test_sigiloso_is_stored_as_null(bronze: MongoBronzeRepository, session: Session) -> None:
    payload = payload_with_numero(1)
    payload["itens"][0] |= {"orcamentoSigiloso": True, "valorUnitarioEstimado": 0}
    _save(bronze, payload, T0)

    _run(bronze, session, T0 + timedelta(hours=1))

    estimado = session.scalar(
        select(ItemContratacaoModel.valor_unitario_estimado).where(
            ItemContratacaoModel.numero_item == 1
        )
    )
    assert estimado is None


def test_second_run_reads_nothing_and_full_rerun_does_not_duplicate(
    bronze: MongoBronzeRepository, session: Session
) -> None:
    _seed(bronze)
    _run(bronze, session, T0 + timedelta(hours=1))

    incremental = _run(bronze, session, T0 + timedelta(hours=2))
    completo = _run(bronze, session, T0 + timedelta(hours=3), completo=True)

    assert incremental.lidas == 0
    assert completo.lidas == 5
    assert _count(session, ContratacaoModel) == 4
    assert _count(session, ItemContratacaoModel) == 11
    # UNIQUE NULLS NOT DISTINCT: a rejeição da contratação (numero_item NULL) não duplica
    assert _count(session, RegistroRejeitadoModel) == 2


def test_new_version_updates_silver_and_removes_dropped_items(
    bronze: MongoBronzeRepository, session: Session
) -> None:
    original = payload_with_numero(1)
    _save(bronze, original, T0)
    _run(bronze, session, T0 + timedelta(hours=1))
    # retificação: objeto mudou e o item 3 saiu
    retificada = copy.deepcopy(original)
    retificada["contratacao"]["objetoCompra"] = "Objeto retificado"
    retificada["itens"] = retificada["itens"][:2]
    _save(bronze, retificada, T0 + timedelta(hours=2))

    report = _run(bronze, session, T0 + timedelta(hours=3))

    assert report.lidas == 1
    contratacao = session.scalars(select(ContratacaoModel)).one()
    assert contratacao.objeto == "Objeto retificado"
    assert _count(session, ItemContratacaoModel) == 2


def test_watermark_is_saved_and_updated(session: Session) -> None:
    uow = SqlSilverUnitOfWork(session)

    assert uow.watermarks.get(PIPELINE) is None
    uow.watermarks.set(PIPELINE, T0)
    uow.watermarks.set(PIPELINE, T0 + timedelta(hours=1))  # upsert: continua 1 linha
    uow.commit()

    assert uow.watermarks.get(PIPELINE) == T0 + timedelta(hours=1)


def test_same_rejection_twice_is_stored_once(session: Session) -> None:
    uow = SqlSilverUnitOfWork(session)
    rejeicao = Rejeicao(
        "x-1", "a" * 64, MotivoRejeicao.CAMPO_INVALIDO, (Problema("contratacao", "erro"),)
    )

    uow.rejeicoes.add(rejeicao)
    uow.rejeicoes.add(rejeicao)
    uow.commit()

    assert _count(session, RegistroRejeitadoModel) == 1
