"""Testes do publicador de eventos com RabbitMQ real."""

import time
from collections.abc import Iterator
from datetime import UTC, datetime

import pika
import pytest
from pika.adapters.blocking_connection import BlockingChannel
from pika.spec import PERSISTENT_DELIVERY_MODE

from radar.adapters.rabbitmq.publisher import (
    EDITAL_NOVO,
    EDITAL_NOVO_DLQ,
    RabbitMqPublisher,
    declare_topology,
)
from radar.events import EditalNovoV1
from radar.ports.events import PublishError


def _event(seq: int = 1) -> EditalNovoV1:
    return EditalNovoV1.for_document(
        numero_controle_pncp="11222333000181-1-000001/2025",
        sequencial_documento=seq,
        caminho=f"x/{seq}.pdf",
        sha256="a" * 64,
        occurred_at=datetime(2025, 9, 1, 12, 0, tzinfo=UTC),
    )


def _get_with_timeout(channel: BlockingChannel, queue: str, timeout: float = 5.0) -> bytes:
    """Espera a mensagem chegar na fila (o dead-lettering do RabbitMQ é assíncrono)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        method, _, body = channel.basic_get(queue, auto_ack=True)
        if method is not None:
            # o stub de tipos do pika declara str, mas o corpo chega como bytes
            assert isinstance(body, bytes)
            return body
        time.sleep(0.05)
    raise AssertionError(f"nenhuma mensagem em {queue} após {timeout}s")


@pytest.fixture
def channel(rabbitmq_params: pika.ConnectionParameters) -> Iterator[BlockingChannel]:
    connection = pika.BlockingConnection(rabbitmq_params)
    yield connection.channel()
    connection.close()


@pytest.fixture
def publisher(rabbitmq_params: pika.ConnectionParameters) -> Iterator[RabbitMqPublisher]:
    publisher = RabbitMqPublisher(rabbitmq_params)
    yield publisher
    publisher.close()


def test_published_event_arrives_persistent_and_valid(
    publisher: RabbitMqPublisher, channel: BlockingChannel
) -> None:
    event = _event()

    publisher.publish(event)

    method, properties, body = channel.basic_get(EDITAL_NOVO, auto_ack=True)
    assert method is not None
    assert properties is not None
    assert isinstance(body, bytes)
    assert EditalNovoV1.model_validate_json(body) == event  # schema correto
    assert properties.delivery_mode == PERSISTENT_DELIVERY_MODE
    assert properties.message_id == str(event.event_id)
    assert properties.content_type == "application/json"
    assert properties.headers == {"schema_version": 1}


def test_rejected_message_goes_to_dead_letter_queue(
    publisher: RabbitMqPublisher, channel: BlockingChannel
) -> None:
    publisher.publish(_event())

    method, _, _ = channel.basic_get(EDITAL_NOVO)
    assert method is not None
    assert method.delivery_tag is not None
    channel.basic_nack(method.delivery_tag, requeue=False)  # o consumidor desistiu dela

    # o nack não espera resposta do broker: a mensagem chega na DLQ logo depois, não na hora
    body = _get_with_timeout(channel, EDITAL_NOVO_DLQ)
    assert EditalNovoV1.model_validate_json(body) == _event()


def test_declare_topology_is_idempotent(channel: BlockingChannel) -> None:
    declare_topology(channel)
    declare_topology(channel)  # declarar de novo com os mesmos argumentos não dá erro

    assert channel.queue_declare(EDITAL_NOVO, passive=True).method.message_count == 0


def test_reconnects_after_connection_is_lost(
    publisher: RabbitMqPublisher, channel: BlockingChannel
) -> None:
    publisher.publish(_event(1))
    publisher.close()  # simula conexão perdida

    publisher.publish(_event(2))

    assert channel.queue_declare(EDITAL_NOVO, passive=True).method.message_count == 2


def test_unreachable_broker_raises_publish_error() -> None:
    params = pika.ConnectionParameters(host="127.0.0.1", port=1, connection_attempts=1)
    publisher = RabbitMqPublisher(params)

    with pytest.raises(PublishError):
        publisher.publish(_event())
