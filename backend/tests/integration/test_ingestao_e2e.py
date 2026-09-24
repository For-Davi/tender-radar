"""Ingestão ponta a ponta: cliente PNCP (HTTP simulado com as fixtures reais) +
MongoDB e RabbitMQ reais + disco temporário. Só a internet é substituída."""

import json
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
import pika
import pytest
import respx
from pymongo.database import Database

from radar.adapters.mongo.bronze import CONTRATACOES, MongoBronzeRepository, MongoDoc
from radar.adapters.pncp.client import PncpClient
from radar.adapters.rabbitmq.publisher import EDITAL_NOVO, RabbitMqPublisher
from radar.adapters.storage.local import LocalDocumentStorage
from radar.events import EditalNovoV1
from radar.services.ingestao import IngestaoService, JanelaIngestao

FIXTURES = Path(__file__).parents[1] / "fixtures" / "pncp"
CONSULTA = "https://pncp.test/api/consulta"
API = "https://pncp.test/api/pncp"
JANELA = JanelaIngestao(date(2025, 3, 10), date(2025, 3, 14), modalidades=(6,), ufs=("CE",))
PDF = b"%PDF-1.7 edital real simulado"


def _fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def pncp_mock() -> Iterator[respx.MockRouter]:
    """Simula o PNCP com as respostas reais gravadas (só a 1ª contratação da página)."""
    page = _fixture("publicacao_pagina.json")
    page["data"] = page["data"][:1]
    page["paginasRestantes"] = 0
    arquivos = _fixture("arquivos.json")
    compra = f"{API}/v1/orgaos/07954480000179/compras/2025/1878"
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{CONSULTA}/v1/contratacoes/publicacao").respond(json=page)
        router.get(f"{compra}/itens").respond(json=_fixture("itens.json"))
        router.get(url__regex=rf"{compra}/itens/\d+/resultados").respond(
            json=_fixture("resultados.json")
        )
        router.get(f"{compra}/arquivos").respond(json=arquivos)
        router.get(arquivos[0]["url"]).respond(content=PDF)
        yield router


@pytest.fixture
def service(
    pncp_mock: respx.MockRouter,
    mongo_db: Database[MongoDoc],
    rabbitmq_params: pika.ConnectionParameters,
    tmp_path: Path,
) -> Iterator[IngestaoService]:
    bronze = MongoBronzeRepository(mongo_db)
    bronze.ensure_indexes()
    publisher = RabbitMqPublisher(rabbitmq_params)
    with httpx.Client() as http:
        source = PncpClient(
            http,
            consulta_url=CONSULTA,
            api_url=API,
            max_attempts=1,
            min_interval_seconds=0,
            max_download_bytes=1_000_000,
        )
        yield IngestaoService(
            source,
            bronze,
            LocalDocumentStorage(tmp_path),
            publisher,
            clock=lambda: datetime(2025, 3, 15, tzinfo=UTC),
        )
    publisher.close()


def _queue_size(params: pika.ConnectionParameters) -> int:
    connection = pika.BlockingConnection(params)
    try:
        count = connection.channel().queue_declare(EDITAL_NOVO, passive=True).method.message_count
        assert count is not None
        return count
    finally:
        connection.close()


def test_ingestion_end_to_end(
    service: IngestaoService,
    mongo_db: Database[MongoDoc],
    rabbitmq_params: pika.ConnectionParameters,
    tmp_path: Path,
) -> None:
    report = service.run(JANELA)

    assert report.falhas == []
    # bronze: o JSON real completo, com itens e resultados
    (doc,) = mongo_db[CONTRATACOES].find()
    assert doc["numero_controle_pncp"] == "07954480000179-1-001878/2025"
    assert len(doc["payload"]["itens"]) == 3
    assert doc["payload"]["resultados"]["1"][0]["niFornecedor"] == "12561319000175"
    # disco: o edital baixado
    assert (tmp_path / "07954480000179/2025/1878/1.pdf").read_bytes() == PDF
    # fila: o evento, no schema certo
    connection = pika.BlockingConnection(rabbitmq_params)
    method, _, body = connection.channel().basic_get(EDITAL_NOVO, auto_ack=True)
    connection.close()
    assert method is not None
    assert isinstance(body, bytes)
    event = EditalNovoV1.model_validate_json(body)
    assert event.caminho == "07954480000179/2025/1878/1.pdf"


def test_ingestion_twice_publishes_once(
    service: IngestaoService,
    mongo_db: Database[MongoDoc],
    rabbitmq_params: pika.ConnectionParameters,
) -> None:
    service.run(JANELA)
    second = service.run(JANELA)

    assert second.versoes_novas == 0
    assert second.eventos_publicados == 0
    assert mongo_db[CONTRATACOES].count_documents({}) == 1
    assert _queue_size(rabbitmq_params) == 1
