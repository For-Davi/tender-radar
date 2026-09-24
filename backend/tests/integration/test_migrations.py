"""Testes das migrações do Alembic contra um Postgres real."""

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Connection, Engine, inspect, text

from radar.adapters.postgres.models import SCHEMA, Base
from tests.integration.conftest import alembic_config

_EXPECTED_TABLES = {"orgao", "fornecedor", "contratacao", "item_contratacao"}


def _silver_schema_exists(conn: Connection) -> bool:
    query = text("SELECT 1 FROM information_schema.schemata WHERE schema_name = 'silver'")
    return conn.execute(query).scalar() is not None


def test_upgrade_head_creates_all_tables(empty_db_engine: Engine) -> None:
    with empty_db_engine.begin() as conn:
        command.upgrade(alembic_config(conn), "head")

        assert set(inspect(conn).get_table_names(schema=SCHEMA)) == _EXPECTED_TABLES


def test_downgrade_base_removes_everything(empty_db_engine: Engine) -> None:
    with empty_db_engine.begin() as conn:
        command.upgrade(alembic_config(conn), "head")
        command.downgrade(alembic_config(conn), "base")

        assert not _silver_schema_exists(conn)


def test_upgrade_again_after_downgrade(empty_db_engine: Engine) -> None:
    # prova que o downgrade não deixa lixo que impeça subir de novo
    with empty_db_engine.begin() as conn:
        config = alembic_config(conn)
        command.upgrade(config, "head")
        command.downgrade(config, "base")
        command.upgrade(config, "head")

        assert set(inspect(conn).get_table_names(schema=SCHEMA)) == _EXPECTED_TABLES


def test_models_match_migrations(empty_db_engine: Engine) -> None:
    """Se alguém mudar um modelo e esquecer de criar a migração, este teste falha."""
    with empty_db_engine.begin() as conn:
        command.upgrade(alembic_config(conn), "head")
        context = MigrationContext.configure(
            conn,
            opts={
                "include_schemas": True,
                "include_name": lambda name, type_, _: type_ != "schema" or name == SCHEMA,
                "compare_type": True,
            },
        )

        assert compare_metadata(context, Base.metadata) == []
