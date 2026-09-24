"""Testes da configuração de logs estruturados."""

import io
import json
from collections.abc import Iterator

import pytest
import structlog

from radar.logging_setup import configure_logging


@pytest.fixture(autouse=True)
def reset_logging() -> Iterator[None]:
    yield
    structlog.reset_defaults()


def test_logging_json_output() -> None:
    stream = io.StringIO()
    configure_logging("INFO", json_output=True, stream=stream)

    structlog.get_logger().info("pedido_recebido", rota="/health")

    record = json.loads(stream.getvalue())  # falha se não for JSON válido
    assert record["event"] == "pedido_recebido"
    assert record["level"] == "info"
    assert record["rota"] == "/health"
    assert "timestamp" in record


def test_logging_one_json_object_per_line() -> None:
    stream = io.StringIO()
    configure_logging("INFO", json_output=True, stream=stream)

    logger = structlog.get_logger()
    logger.info("primeiro")
    logger.info("segundo")

    lines = stream.getvalue().strip().splitlines()
    assert [json.loads(line)["event"] for line in lines] == ["primeiro", "segundo"]


def test_logging_respects_level() -> None:
    stream = io.StringIO()
    configure_logging("INFO", json_output=True, stream=stream)

    logger = structlog.get_logger()
    logger.debug("nao_deve_aparecer")
    logger.warning("deve_aparecer")

    output = stream.getvalue()
    assert "nao_deve_aparecer" not in output
    assert "deve_aparecer" in output


def test_logging_console_output_is_human_readable() -> None:
    stream = io.StringIO()
    configure_logging("DEBUG", json_output=False, stream=stream)

    structlog.get_logger().debug("modo_dev", valor=42)

    output = stream.getvalue()
    assert "modo_dev" in output
    assert "valor=42" in output
    with pytest.raises(json.JSONDecodeError):
        json.loads(output)


def test_logging_includes_exception_traceback_in_json() -> None:
    stream = io.StringIO()
    configure_logging("INFO", json_output=True, stream=stream)

    try:
        raise ValueError("falhou")
    except ValueError:
        structlog.get_logger().exception("erro_inesperado")

    record = json.loads(stream.getvalue())
    assert record["level"] == "error"
    assert "ValueError: falhou" in record["exception"]
