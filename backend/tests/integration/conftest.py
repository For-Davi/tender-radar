"""Fixtures de integração com serviços reais (testcontainers) e a API sobre eles."""

import uuid
from collections.abc import Iterator
from pathlib import Path

import pika
import pytest
import structlog
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pymongo import MongoClient
from pymongo.database import Database
from sqlalchemy import Connection, Engine, create_engine, make_url, text
from sqlalchemy.orm import Session
from testcontainers.community.mongodb import MongoDbContainer
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.rabbitmq import RabbitMqContainer

from radar.adapters.mongo.bronze import MongoDoc
from radar.adapters.postgres.gold import GOLD_METADATA
from radar.adapters.rabbitmq.publisher import EDITAL_NOVO, EDITAL_NOVO_DLQ
from radar.api.main import create_app
from radar.config import Settings

_BACKEND_DIR = Path(__file__).parents[2]
_TABLES = (
    "silver.item_contratacao, silver.contratacao, silver.fornecedor, silver.orgao, "
    "silver.registros_rejeitados, silver.pipeline_watermark"
)


def alembic_config(connection: Connection) -> Config:
    """Config do Alembic usando uma conexão já aberta (ver alembic/env.py)."""
    config = Config(str(_BACKEND_DIR / "alembic.ini"))
    config.attributes["connection"] = connection
    config.attributes["configure_logger"] = False
    return config


@pytest.fixture(scope="session")
def pg_container() -> Iterator[PostgresContainer]:
    # scope="session": um container para todos os testes (subir um leva alguns segundos)
    with PostgresContainer("pgvector/pgvector:pg16", driver="psycopg") as container:
        yield container


@pytest.fixture(scope="session")
def engine(pg_container: PostgresContainer) -> Iterator[Engine]:
    """Engine do banco principal, já com todas as migrações aplicadas."""
    engine = create_engine(pg_container.get_connection_url())
    with engine.begin() as conn:
        command.upgrade(alembic_config(conn), "head")
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    """Sessão limpa por teste: no fim, apaga os dados (TRUNCATE) para o próximo teste."""
    with Session(engine, expire_on_commit=False) as session:
        yield session
        session.rollback()
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {_TABLES} RESTART IDENTITY CASCADE"))


@pytest.fixture
def empty_db_engine(pg_container: PostgresContainer) -> Iterator[Engine]:
    """Banco novo e vazio, só deste teste (para testar as migrações do zero)."""
    admin = create_engine(pg_container.get_connection_url(), isolation_level="AUTOCOMMIT")
    name = f"test_{uuid.uuid4().hex[:12]}"
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    engine = create_engine(make_url(pg_container.get_connection_url()).set(database=name))
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE "{name}"'))
        admin.dispose()


# ------------------------------------------------------------------ Mongo e RabbitMQ


@pytest.fixture(scope="session")
def mongo_container() -> Iterator[MongoDbContainer]:
    with MongoDbContainer("mongo:7") as container:
        yield container


@pytest.fixture
def mongo_db(mongo_container: MongoDbContainer) -> Iterator[Database[MongoDoc]]:
    """Banco Mongo novo por teste (nome aleatório), apagado no final."""
    # tz_aware=True: datas voltam com fuso (UTC), iguais às que foram gravadas
    client: MongoClient[MongoDoc] = MongoClient(mongo_container.get_connection_url(), tz_aware=True)
    db = client[f"test_{uuid.uuid4().hex[:12]}"]
    try:
        yield db
    finally:
        client.drop_database(db.name)
        client.close()


@pytest.fixture(scope="session")
def rabbitmq_container() -> Iterator[RabbitMqContainer]:
    with RabbitMqContainer("rabbitmq:3.13-management") as container:
        yield container


@pytest.fixture
def rabbitmq_params(rabbitmq_container: RabbitMqContainer) -> Iterator[pika.ConnectionParameters]:
    """Parâmetros de conexão; as filas do projeto são esvaziadas depois de cada teste."""
    params = rabbitmq_container.get_connection_params()
    yield params
    connection = pika.BlockingConnection(params)
    channel = connection.channel()
    for queue in (EDITAL_NOVO, EDITAL_NOVO_DLQ):
        # queue_declare passivo falha se a fila não existe; então só purga se existir
        try:
            channel.queue_purge(queue)
        except pika.exceptions.ChannelClosedByBroker:
            channel = connection.channel()
    connection.close()


# ------------------------------------------------------------------ API


@pytest.fixture
def api_client(engine: Engine) -> Iterator[TestClient]:
    """A app de verdade (rotas, adapters SQL) usando o Postgres do container."""
    app = create_app(Settings(app_name="radar-integracao"), engine=engine)
    yield TestClient(app)
    structlog.reset_defaults()


@pytest.fixture
def gold(engine: Engine) -> Iterator[Engine]:
    """Schema gold com as tabelas descritas em `gold.py` (no projeto, quem cria é o dbt).

    O teste de contrato (`tests/contract/`) garante que esta descrição bate com o dbt.
    """
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA gold"))
        GOLD_METADATA.create_all(conn)
    yield engine
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA gold CASCADE"))
