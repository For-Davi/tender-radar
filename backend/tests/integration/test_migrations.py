"""Testes das migrações do Alembic contra um Postgres real."""

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Connection, Engine, inspect, text
from sqlalchemy.exc import IntegrityError

from radar.adapters.postgres.models import SCHEMA, Base
from tests.integration.conftest import alembic_config

_EXPECTED_TABLES = {
    "orgao",
    "fornecedor",
    "contratacao",
    "item_contratacao",
    "registros_rejeitados",
    "pipeline_watermark",
}


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


def test_downgrade_0002_refuses_to_invent_zero_for_unknown_estimate(
    empty_db_engine: Engine,
) -> None:
    """Com item sigiloso (NULL) no banco, voltar para a 0001 falha em vez de gravar 0."""
    with empty_db_engine.connect() as conn:
        config = alembic_config(conn)
        command.upgrade(config, "head")
        conn.execute(
            text(
                "INSERT INTO silver.orgao (cnpj, razao_social, esfera, poder) "
                "VALUES (:cnpj, :nome, :esfera, :poder)"
            ),
            {"cnpj": "11222333000181", "nome": "Órgão", "esfera": "M", "poder": "E"},
        )
        conn.execute(
            text(
                "INSERT INTO silver.contratacao (numero_controle_pncp, orgao_id, ano, sequencial,"
                " modalidade, situacao, objeto, data_publicacao, uf, municipio) VALUES"
                " (:numero, 1, 2026, 1, 6, 1, :objeto, now(), :uf, :municipio)"
            ),
            {"numero": "11222333000181-1-000001/2026", "objeto": "x", "uf": "CE", "municipio": "y"},
        )
        conn.execute(
            text(
                "INSERT INTO silver.item_contratacao (contratacao_id, numero_item, descricao,"
                " material_ou_servico, quantidade, unidade_medida, valor_unitario_estimado)"
                " VALUES (1, 1, :descricao, :tipo, 1, :unidade, NULL)"
            ),
            {"descricao": "item sigiloso", "tipo": "M", "unidade": "UN"},
        )

        with pytest.raises(IntegrityError, match="valor_unitario_estimado"):
            command.downgrade(config, "0001")
        conn.rollback()
