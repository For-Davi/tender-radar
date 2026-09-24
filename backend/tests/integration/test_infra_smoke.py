"""Testes de fumaça da infraestrutura, com containers reais (testcontainers).

Cada fixture sobe um container descartável com a MESMA imagem do docker-compose,
e ele é destruído no fim do módulo. Os testes não dependem do `make up`.
"""

from collections.abc import Iterator
from pathlib import Path

import pika
import psycopg
import pytest
from pymongo import MongoClient
from testcontainers.community.mongodb import MongoDbContainer
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.rabbitmq import RabbitMqContainer

from radar.config import Settings

_INIT_SQL = Path(__file__).parents[3] / "infra" / "postgres" / "init.sql"


@pytest.fixture(scope="module")
def postgres() -> Iterator[PostgresContainer]:
    with PostgresContainer("pgvector/pgvector:pg16", driver=None) as container:
        yield container


@pytest.fixture(scope="module")
def mongo() -> Iterator[MongoDbContainer]:
    with MongoDbContainer("mongo:7") as container:
        yield container


@pytest.fixture(scope="module")
def rabbitmq() -> Iterator[RabbitMqContainer]:
    with RabbitMqContainer("rabbitmq:3.13-management") as container:
        yield container


def _settings_for(container: PostgresContainer) -> Settings:
    """Settings apontando para o container, montadas como a app faria."""
    return Settings(
        postgres_host=container.get_container_host_ip(),
        postgres_port=int(container.get_exposed_port(5432)),
        postgres_user=container.username,
        postgres_password=container.password,
        postgres_db=container.dbname,
    )


def test_postgres_select_1_and_vector_extension(postgres: PostgresContainer) -> None:
    dsn = _settings_for(postgres).postgres_dsn  # prova também que a DSN de Settings funciona

    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(_INIT_SQL.read_text())  # executa o NOSSO init.sql, não um SQL do teste
        select_one = conn.execute("SELECT 1").fetchone()
        extension = conn.execute(
            "SELECT extname FROM pg_extension WHERE extname = 'vector'"
        ).fetchone()

    assert select_one == (1,)
    assert extension == ("vector",)


def test_postgres_init_sql_is_idempotent(postgres: PostgresContainer) -> None:
    # IF NOT EXISTS: rodar duas vezes não pode dar erro
    with psycopg.connect(_settings_for(postgres).postgres_dsn, autocommit=True) as conn:
        conn.execute(_INIT_SQL.read_text())
        conn.execute(_INIT_SQL.read_text())


def test_mongo_ping(mongo: MongoDbContainer) -> None:
    client: MongoClient[dict[str, object]] = MongoClient(mongo.get_connection_url())
    try:
        assert client.admin.command("ping")["ok"] == 1.0
    finally:
        client.close()


def test_rabbitmq_accepts_connection_and_declares_queue(rabbitmq: RabbitMqContainer) -> None:
    connection = pika.BlockingConnection(rabbitmq.get_connection_params())
    try:
        channel = connection.channel()
        # exclusive: fila temporária, apagada quando a conexão fecha
        result = channel.queue_declare(queue="", exclusive=True)
        queue_name = result.method.queue
        assert queue_name is not None
        assert queue_name.startswith("amq.gen-")  # nome gerado pelo broker
    finally:
        connection.close()
