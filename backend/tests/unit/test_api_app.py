"""Testes da montagem da app (engine e lifespan) e da tradução de erros da gold."""

from collections.abc import Iterator

import pytest
import structlog
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.exc import ProgrammingError

from radar.adapters.postgres.gold import _gold_disponivel
from radar.api.main import create_app
from radar.config import Settings
from radar.ports.metricas import AnaliticoIndisponivelError


@pytest.fixture(autouse=True)
def reset_logging() -> Iterator[None]:
    yield
    structlog.reset_defaults()


def test_app_disposes_the_engine_it_created(monkeypatch: pytest.MonkeyPatch) -> None:
    disposed: list[Engine] = []
    monkeypatch.setattr(Engine, "dispose", lambda self, close=True: disposed.append(self))

    # o "with" roda o lifespan: startup na entrada, shutdown na saída
    with TestClient(create_app(Settings())):
        assert disposed == []

    assert len(disposed) == 1


def test_app_does_not_dispose_an_injected_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    # o engine injetado é de quem o criou (ex.: a fixture dos testes de integração)
    engine = create_engine("sqlite://")
    disposed: list[Engine] = []
    monkeypatch.setattr(Engine, "dispose", lambda self, close=True: disposed.append(self))

    with TestClient(create_app(Settings(), engine=engine)):
        pass

    assert disposed == []


# ------------------------------------------------------------------ gold indisponível


class _PgError(Exception):
    """Imita o erro do psycopg, que expõe o código SQLSTATE em `.sqlstate`."""

    def __init__(self, sqlstate: str) -> None:
        super().__init__(f"erro {sqlstate}")
        self.sqlstate = sqlstate


def _programming_error(sqlstate: str) -> ProgrammingError:
    return ProgrammingError("SELECT ...", {}, _PgError(sqlstate))


@pytest.mark.parametrize("sqlstate", ["42P01", "3F000"])  # tabela / schema não existe
def test_missing_gold_becomes_port_error(sqlstate: str) -> None:
    with pytest.raises(AnaliticoIndisponivelError), _gold_disponivel():
        raise _programming_error(sqlstate)


def test_other_sql_errors_are_not_hidden() -> None:
    # 42703 = coluna não existe: é bug (contrato com o dbt quebrado), não "indisponível"
    with pytest.raises(ProgrammingError), _gold_disponivel():
        raise _programming_error("42703")
