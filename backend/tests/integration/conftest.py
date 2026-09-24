"""Fixtures de integração com Postgres real (testcontainers)."""

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, create_engine, make_url, text
from sqlalchemy.orm import Session
from testcontainers.community.postgres import PostgresContainer

_BACKEND_DIR = Path(__file__).parents[2]
_TABLES = "silver.item_contratacao, silver.contratacao, silver.fornecedor, silver.orgao"


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
