"""Testes do formato padronizado de erro (problem+json) e do CORS."""

import io
import json
from http import HTTPStatus

import pytest
import structlog
from fastapi import FastAPI
from fastapi.testclient import TestClient

from radar.api.dependencies import get_contratacao_queries
from radar.logging_setup import configure_logging


class _Boom:
    """Port que explode com um erro inesperado (ex.: bug ou banco fora do ar)."""

    def listar(self, *_: object) -> None:
        raise RuntimeError("senha=segredo; SELECT * FROM silver.contratacao")


@pytest.mark.parametrize(
    ("method", "path", "status"),
    [
        ("GET", "/rota-que-nao-existe", 404),
        ("POST", "/contratacoes", 405),
        ("GET", "/contratacoes?uf=XX", 422),
    ],
)
def test_errors_use_problem_json(api: TestClient, method: str, path: str, status: int) -> None:
    response = api.request(method, path)

    assert response.status_code == status
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    # title = frase padrão do status (no Python 3.12, 422 = "Unprocessable Entity")
    assert (body["type"], body["title"], body["status"]) == (
        "about:blank",
        HTTPStatus(status).phrase,
        status,
    )
    assert body["instance"] == path.split("?")[0]


def test_405_keeps_allow_header(api: TestClient) -> None:
    response = api.post("/contratacoes")

    assert response.headers["allow"] == "GET"


def test_default_404_has_no_redundant_detail(api: TestClient) -> None:
    # o detail padrão do Starlette seria "Not Found", igual ao title: fica de fora
    assert "detail" not in api.get("/nao-existe").json()


def test_422_lists_every_invalid_field(api: TestClient) -> None:
    response = api.get("/contratacoes", params={"uf": "XX", "pagina": "0"})

    body = response.json()
    assert body["detail"] == "parâmetros inválidos"
    assert {erro["campo"] for erro in body["erros"]} == {"query.uf", "query.pagina"}
    assert all(erro["mensagem"] for erro in body["erros"])


def test_unexpected_error_returns_generic_500_and_logs_details(app: FastAPI) -> None:
    stream = io.StringIO()
    configure_logging("INFO", json_output=True, stream=stream)
    app.dependency_overrides[get_contratacao_queries] = _Boom
    # raise_server_exceptions=False: o TestClient devolve a resposta em vez de relançar
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/contratacoes")

    assert response.status_code == 500
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["detail"] == "erro interno; tente novamente mais tarde"
    assert "segredo" not in response.text  # nada interno vaza para o cliente
    # ...mas o log tem o necessário para depurar
    log = json.loads(stream.getvalue().strip().splitlines()[-1])
    assert log["event"] == "erro_inesperado"
    assert log["path"] == "/contratacoes"
    assert "RuntimeError" in log["exception"]
    structlog.reset_defaults()


# ------------------------------------------------------------------ CORS


def test_cors_preflight_from_allowed_origin(api: TestClient) -> None:
    response = api.options(
        "/contratacoes",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_cors_simple_request_from_allowed_origin(api: TestClient) -> None:
    response = api.get("/health", headers={"Origin": "http://localhost:3000"})

    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_cors_rejects_other_origin(api: TestClient) -> None:
    response = api.options(
        "/contratacoes",
        headers={"Origin": "https://site-malicioso.com", "Access-Control-Request-Method": "GET"},
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_cors_only_allows_get(api: TestClient) -> None:
    response = api.options(
        "/contratacoes",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "DELETE"},
    )

    assert response.status_code == 400


def test_422_message_has_no_pydantic_prefix(api: TestClient) -> None:
    # bug achado na execução real: "Value error, UF inválida: 'XX'"
    erro = api.get("/contratacoes", params={"uf": "XX"}).json()["erros"][0]

    assert erro["mensagem"] == "UF inválida: 'XX'"


def test_422_cross_field_message_has_no_pydantic_prefix(api: TestClient) -> None:
    params = {"valor_min": "2", "valor_max": "1"}

    erro = api.get("/contratacoes", params=params).json()["erros"][0]

    assert erro == {"campo": "query", "mensagem": "valor_min não pode ser maior que valor_max"}
