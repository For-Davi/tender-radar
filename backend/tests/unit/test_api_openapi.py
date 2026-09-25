"""Teste de contrato: o schema OpenAPI é gerado, é válido e documenta os erros.

O frontend (Etapa 06) vai gerar os tipos TypeScript a partir deste schema. Um schema
inválido ou incompleto quebraria o frontend, então ele é testado como código.
"""

from typing import Any

import pytest
from fastapi import FastAPI
from openapi_spec_validator import validate

ROTAS = {
    "/contratacoes": {422},
    "/contratacoes/{id}": {404, 422},
    "/orgaos": {422},
    "/categorias": {503},
    "/metricas/valor-mensal": {503},
    "/metricas/preco-categoria": {422, 503},
    "/metricas/ranking-fornecedores": {422, 503},
    "/metricas/precos-acima-p90": {422, 503},
}


@pytest.fixture
def schema(app: FastAPI) -> dict[str, Any]:
    return app.openapi()


def test_schema_is_valid_openapi(schema: dict[str, Any]) -> None:
    # levanta OpenAPIValidationError se o documento violar a especificação
    validate(schema)
    assert schema["openapi"].startswith("3.1")


def test_all_routes_are_documented(schema: dict[str, Any]) -> None:
    assert set(ROTAS) | {"/health"} == set(schema["paths"])


@pytest.mark.parametrize(("path", "erros"), ROTAS.items())
def test_error_responses_are_documented_as_problem_json(
    schema: dict[str, Any], path: str, erros: set[int]
) -> None:
    responses = schema["paths"][path]["get"]["responses"]

    assert "200" in responses
    for status in erros:
        content = responses[str(status)]["content"]
        # só problem+json: o 422 padrão do FastAPI (HTTPValidationError) foi substituído
        assert set(content) == {"application/problem+json"}
        assert content["application/problem+json"]["schema"] == {
            "$ref": "#/components/schemas/ProblemDetail"
        }


def test_money_fields_are_strings_in_responses(schema: dict[str, Any]) -> None:
    contratacao = schema["components"]["schemas"]["ContratacaoResponse"]["properties"]
    valor = contratacao["valor_total_estimado"]

    # Decimal na resposta é texto (com padrão numérico) ou null; nunca "number"
    tipos = {opcao.get("type") for opcao in valor["anyOf"]}
    assert tipos == {"string", "null"}


def test_every_route_has_a_summary_description(schema: dict[str, Any]) -> None:
    for path in ROTAS:
        assert schema["paths"][path]["get"].get("description"), path
