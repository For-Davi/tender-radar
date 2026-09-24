"""Testes da rota /health e da factory da aplicação."""

from collections.abc import Iterator

import pytest
import structlog
from fastapi.testclient import TestClient

from radar.api.main import create_app
from radar.config import Settings


@pytest.fixture(autouse=True)
def reset_logging() -> Iterator[None]:
    # create_app configura o structlog globalmente; restauramos o padrão depois
    yield
    structlog.reset_defaults()


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(Settings(app_name="radar-teste")))


def test_health_returns_200_and_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "quebrado"}


def test_health_is_json(client: TestClient) -> None:
    response = client.get("/health")

    assert response.headers["content-type"] == "application/json"


def test_unknown_route_returns_404(client: TestClient) -> None:
    assert client.get("/nao-existe").status_code == 404


def test_health_rejects_post(client: TestClient) -> None:
    assert client.post("/health").status_code == 405


def test_create_app_uses_injected_settings() -> None:
    settings = Settings(app_name="outro-nome")

    app = create_app(settings)

    assert app.title == "outro-nome"
    assert app.state.settings is settings
