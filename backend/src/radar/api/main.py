"""Ponto de entrada da API.

`create_app` é uma factory: recebe as settings por parâmetro (injeção de dependência),
o que permite aos testes criar uma app com configuração própria. O `app` do fim do
arquivo é o que o uvicorn carrega: `uvicorn radar.api.main:app`.
"""

from importlib.metadata import version

import structlog
from fastapi import FastAPI

from radar.api.health import router as health_router
from radar.config import Settings
from radar.logging_setup import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings.log_level, json_output=settings.log_json)

    app = FastAPI(title=settings.app_name, version=version("radar"))
    app.state.settings = settings
    app.include_router(health_router)

    structlog.get_logger().info("app_criada", environment=settings.environment)
    return app


app = create_app()
