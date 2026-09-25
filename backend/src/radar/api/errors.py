"""Erros da API no formato padrão "problem details" (RFC 9457).

Todo erro sai com o mesmo formato e o content-type `application/problem+json`:

    {"type": "about:blank", "title": "Not Found", "status": 404,
     "detail": "contratação não encontrada: ...", "instance": "/contratacoes/..."}

Um formato único permite ao frontend tratar qualquer erro com o mesmo código. Em
erros de validação (422), o campo extra `erros` lista cada parâmetro inválido.

Os handlers são registrados em `create_app` (`register_error_handlers`).
"""

from collections.abc import Mapping
from http import HTTPStatus
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from radar.ports.metricas import AnaliticoIndisponivelError

PROBLEM_JSON = "application/problem+json"

_log = structlog.get_logger()


class ErroCampo(BaseModel):
    campo: str  # ex.: "query.uf" ou "path.id"
    mensagem: str


class ProblemDetail(BaseModel):
    type: str = "about:blank"  # "about:blank" = o significado é o do próprio status HTTP
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None  # o caminho da requisição que falhou
    erros: list[ErroCampo] | None = None


def problem_response(
    request: Request,
    status: int,
    detail: str | None = None,
    *,
    erros: list[ErroCampo] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    problem = ProblemDetail(
        title=HTTPStatus(status).phrase,
        status=status,
        detail=detail,
        instance=request.url.path,
        erros=erros,
    )
    return JSONResponse(
        problem.model_dump(exclude_none=True),
        status_code=status,
        media_type=PROBLEM_JSON,
        headers=headers,
    )


_PROBLEM_REF = {"$ref": "#/components/schemas/ProblemDetail"}


def problem_responses(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """Documenta respostas de erro no OpenAPI (parâmetro `responses` das rotas).

    Não usa `"model": ProblemDetail`: com ele, o FastAPI documentaria o erro também
    como `application/json` (o tipo padrão da rota), o que não é verdade. O schema
    referenciado aqui é registrado por `register_problem_schema`.
    """
    return {
        status: {
            "description": HTTPStatus(status).phrase,
            "content": {PROBLEM_JSON: {"schema": _PROBLEM_REF}},
        }
        for status in statuses
    }


def register_problem_schema(app: FastAPI) -> None:
    """Acrescenta `ProblemDetail` (e o `ErroCampo`) aos componentes do schema OpenAPI."""
    generate = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            schema = generate()  # gera e guarda em app.openapi_schema (cache)
            problem = ProblemDetail.model_json_schema(ref_template="#/components/schemas/{model}")
            components = schema.setdefault("components", {}).setdefault("schemas", {})
            components.update(problem.pop("$defs", {}))
            components["ProblemDetail"] = problem
        return app.openapi_schema or generate()

    # é o jeito documentado pelo FastAPI de personalizar o OpenAPI, e o mypy não
    # aceita trocar um método de uma instância
    app.openapi = openapi  # type: ignore[method-assign]


# ------------------------------------------------------------------ handlers


def _http_exception(request: Request, exc: Exception) -> JSONResponse:
    # o Starlette tipa todo handler com "Exception"; o registro garante o tipo certo
    if not isinstance(exc, StarletteHTTPException):
        raise exc
    # detail padrão do Starlette é a própria frase do status ("Not Found"): não repetir
    detail = exc.detail if exc.detail != HTTPStatus(exc.status_code).phrase else None
    # headers: o 405 precisa manter o "Allow" (quais métodos a rota aceita)
    return problem_response(request, exc.status_code, detail, headers=exc.headers)


def _mensagem(error: Mapping[str, Any]) -> str:
    """Texto do erro para o usuário.

    Nos validadores nossos (ValueError), o Pydantic prefixa "Value error, " na `msg`;
    a exceção original, sem prefixo, fica em `ctx["error"]`.
    """
    original = error.get("ctx", {}).get("error")
    if error.get("type") == "value_error" and isinstance(original, ValueError):
        return str(original)
    return str(error["msg"])


def _validation_error(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise exc
    erros = [
        ErroCampo(campo=".".join(str(part) for part in error["loc"]), mensagem=_mensagem(error))
        for error in exc.errors()
    ]
    return problem_response(request, 422, "parâmetros inválidos", erros=erros)


def _analitico_indisponivel(request: Request, exc: Exception) -> JSONResponse:
    _log.warning("gold_indisponivel", path=request.url.path, erro=str(exc))
    return problem_response(
        request,
        503,
        "camada analítica indisponível: os marts do dbt ainda não foram gerados",
        headers={"Retry-After": "60"},
    )


def _unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    # o detalhe vai só para o log: a mensagem da exceção pode conter SQL, caminhos etc.
    _log.error("erro_inesperado", path=request.url.path, exc_info=exc)
    return problem_response(request, 500, "erro interno; tente novamente mais tarde")


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, _http_exception)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(AnaliticoIndisponivelError, _analitico_indisponivel)
    app.add_exception_handler(Exception, _unexpected_error)
