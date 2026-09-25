"""Ponto de entrada da API.

`create_app` é uma factory: recebe as settings (e, opcionalmente, o engine do banco)
por parâmetro, o que permite aos testes criar uma app com configuração própria. O
`app` do fim do arquivo é o que o uvicorn carrega: `uvicorn radar.api.main:app`.

Criar o engine não abre conexão: a primeira conexão só acontece na primeira
requisição que usa o banco. Por isso importar este módulo não exige Postgres no ar.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import version

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import Engine

from radar.adapters.postgres.database import create_db_engine, create_session_factory
from radar.api.errors import register_error_handlers, register_problem_schema
from radar.api.health import router as health_router
from radar.api.routers.categorias import router as categorias_router
from radar.api.routers.contratacoes import router as contratacoes_router
from radar.api.routers.metricas import router as metricas_router
from radar.api.routers.orgaos import router as orgaos_router
from radar.config import Settings
from radar.logging_setup import configure_logging

_DESCRIPTION = """
Contratações públicas do PNCP, limpas (camada silver) e analisadas (camada gold).

- **Erros** seguem o formato `application/problem+json` (RFC 9457).
- **Dinheiro** é enviado como texto decimal (`"1234.5600"`), nunca como float.
- **Datas** de filtro são dias no horário de Brasília.
"""


def create_app(settings: Settings | None = None, *, engine: Engine | None = None) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings.log_level, json_output=settings.log_json)
    owns_engine = engine is None
    db_engine = engine or create_db_engine(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        # no desligamento: fecha as conexões do pool (só se o engine for nosso)
        if owns_engine:
            db_engine.dispose()

    app = FastAPI(
        title=settings.app_name,
        version=version("radar"),
        description=_DESCRIPTION,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.session_factory = create_session_factory(db_engine)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET"],  # a API é só de leitura
        allow_headers=["*"],
    )
    register_error_handlers(app)
    register_problem_schema(app)

    app.include_router(health_router)
    app.include_router(contratacoes_router)
    app.include_router(orgaos_router)
    app.include_router(categorias_router)
    app.include_router(metricas_router)

    structlog.get_logger().info("app_criada", environment=settings.environment)
    return app


app = create_app()
