"""Contrato entre a API e a camada gold gerada pelo dbt.

A API descreve em `adapters/postgres/gold.py` as colunas que lê da gold. Quem cria
essas tabelas é o dbt, então nada impede alguém de renomear uma coluna num modelo
do dbt e quebrar a API sem perceber: os testes de integração da API criam a gold a
partir da MESMA descrição, e continuariam verdes.

Este teste fecha esse buraco: roda contra um banco onde o `dbt build` já rodou
(no CI: job `dbt`; local: `make test-contract`) e compara a descrição com as
tabelas reais. Conexão pelas variáveis de ambiente de sempre (`POSTGRES_*`).
"""

from collections.abc import Iterator
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import Engine, Table, inspect
from sqlalchemy.orm import Session
from sqlalchemy.types import TypeEngine

from radar.adapters.postgres.database import create_db_engine
from radar.adapters.postgres.gold import GOLD_METADATA, GOLD_SCHEMA, SqlMetricasQueries
from radar.config import Settings
from radar.ports.consultas import PaginaPedido

TABELAS = sorted(GOLD_METADATA.tables.values(), key=lambda table: table.name)


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    engine = create_db_engine(Settings())
    yield engine
    engine.dispose()


def _python_type(sql_type: TypeEngine[Any]) -> type:
    """Tipo Python que o driver devolve: é o que a API realmente consome."""
    return sql_type.python_type


@pytest.mark.parametrize("table", TABELAS, ids=lambda table: table.name)
def test_gold_table_has_the_columns_the_api_reads(engine: Engine, table: Table) -> None:
    inspector = inspect(engine)
    assert inspector.has_table(table.name, schema=GOLD_SCHEMA), (
        f"{GOLD_SCHEMA}.{table.name} não existe: rode o dbt build antes deste teste"
    )
    reais = {col["name"]: col["type"] for col in inspector.get_columns(table.name, GOLD_SCHEMA)}

    faltando = [col.name for col in table.columns if col.name not in reais]
    assert faltando == [], f"colunas que a API lê e o dbt não gera em {table.name}"

    incompativeis = {
        col.name: (str(col.type), str(reais[col.name]))
        for col in table.columns
        if _python_type(col.type) is not _python_type(reais[col.name])
    }
    assert incompativeis == {}, f"tipos diferentes em {table.name} (declarado, real)"


def test_contract_covers_types_the_api_expects() -> None:
    # sanidade do próprio teste: se a descrição usar um tipo sem python_type,
    # a comparação acima quebraria com um erro confuso
    tipos = {_python_type(col.type) for table in TABELAS for col in table.columns}
    assert tipos <= {str, int, Decimal, date, datetime, bool}


def test_every_metric_query_runs_on_the_real_gold(engine: Engine) -> None:
    # nomes certos não bastam: os joins e filtros precisam rodar nas tabelas do dbt
    with Session(engine) as session:
        queries = SqlMetricasQueries(session)
        queries.categorias()
        queries.valor_mensal()
        queries.preco_categoria(None)
        queries.preco_categoria("30")
        queries.ranking_fornecedores(None)
        queries.ranking_fornecedores("11222333000181")
        pagina = queries.precos_acima_p90(PaginaPedido(1, 5))

    assert pagina.total >= 0
