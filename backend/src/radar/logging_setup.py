"""Configuração de logs estruturados com structlog.

Log estruturado = cada evento é um dicionário (`evento` + campos), não uma frase solta.
Em desenvolvimento ele é impresso de forma legível; em container, como JSON
(uma linha por evento), que ferramentas de log conseguem filtrar por campo.
"""

import logging
import sys
from typing import TextIO

import structlog

from radar.config import LogLevel

_LEVELS: dict[LogLevel, int] = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
}


def configure_logging(level: LogLevel, *, json_output: bool, stream: TextIO | None = None) -> None:
    """Configura o structlog globalmente.

    `stream` existe para os testes capturarem a saída; em produção é o stdout.
    """
    processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,  # campos de contexto (ex.: id da requisição)
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]
    if json_output:
        # traceback vira texto dentro do campo "exception" do JSON
        processors += [structlog.processors.format_exc_info, structlog.processors.JSONRenderer()]
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=False))

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(_LEVELS[level]),
        logger_factory=structlog.PrintLoggerFactory(file=stream or sys.stdout),
        cache_logger_on_first_use=False,
    )
