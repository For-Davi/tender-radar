"""Fixtures dos testes unitários da API: a app de verdade, com os ports trocados por fakes.

Ficam no conftest.py da pasta: o pytest as disponibiliza para todos os testes daqui.

`app.dependency_overrides` é o mecanismo do FastAPI para injeção de dependência em
testes: onde a rota pede `get_contratacao_queries`, recebe o fake. O código das rotas,
schemas e handlers de erro roda inteiro; só o acesso ao banco é substituído.
"""

from collections.abc import Iterator

import pytest
import structlog
from fastapi import FastAPI
from fastapi.testclient import TestClient

from radar.api.dependencies import (
    get_contratacao_queries,
    get_metricas_queries,
    get_orgao_queries,
)
from radar.api.main import create_app
from radar.config import Settings
from tests.fakes_consultas import FakeContratacaoQueries, FakeMetricasQueries, FakeOrgaoQueries


@pytest.fixture
def fake_contratacoes() -> FakeContratacaoQueries:
    return FakeContratacaoQueries()


@pytest.fixture
def fake_orgaos() -> FakeOrgaoQueries:
    return FakeOrgaoQueries()


@pytest.fixture
def fake_metricas() -> FakeMetricasQueries:
    return FakeMetricasQueries()


@pytest.fixture
def app(
    fake_contratacoes: FakeContratacaoQueries,
    fake_orgaos: FakeOrgaoQueries,
    fake_metricas: FakeMetricasQueries,
) -> Iterator[FastAPI]:
    app = create_app(Settings(app_name="radar-teste", cors_origins=["http://localhost:3000"]))
    app.dependency_overrides[get_contratacao_queries] = lambda: fake_contratacoes
    app.dependency_overrides[get_orgao_queries] = lambda: fake_orgaos
    app.dependency_overrides[get_metricas_queries] = lambda: fake_metricas
    yield app
    # create_app configura o structlog globalmente; restauramos o padrão depois
    structlog.reset_defaults()


@pytest.fixture
def api(app: FastAPI) -> TestClient:
    return TestClient(app)
