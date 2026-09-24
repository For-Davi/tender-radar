"""Publicação de eventos no RabbitMQ.

Topologia (declarada por `declare_topology`, idempotente):

    radar.eventos (exchange topic) --"edital.novo"--> fila edital.novo
                                                          | rejeitada / expirada
                                                          v
    radar.dlx (exchange topic)     --"edital.novo"--> fila edital.novo.dlq

- exchange: recebe a mensagem e decide para qual fila vai, pela routing key;
- fila durável + mensagem persistente: sobrevivem a um restart do broker;
- dead-letter: a mensagem que o consumidor rejeitar vai para a DLQ, em vez de sumir.
"""

import pika
import structlog
from pika.adapters.blocking_connection import BlockingChannel
from pika.exceptions import AMQPError
from pika.exchange_type import ExchangeType
from pika.spec import PERSISTENT_DELIVERY_MODE

from radar.events import EditalNovoV1
from radar.ports.events import PublishError

EXCHANGE = "radar.eventos"
DEAD_LETTER_EXCHANGE = "radar.dlx"
EDITAL_NOVO = "edital.novo"  # routing key e nome da fila
EDITAL_NOVO_DLQ = "edital.novo.dlq"

log = structlog.get_logger()


# ExchangeType("topic") e não ExchangeType.topic: o stub de tipos do pika declara os membros
# como `topic: str`, e o mypy os lê como atributos str. Buscar pelo valor dá o tipo certo.
_TOPIC = ExchangeType("topic")


def declare_topology(channel: BlockingChannel) -> None:
    channel.exchange_declare(EXCHANGE, exchange_type=_TOPIC, durable=True)
    channel.exchange_declare(DEAD_LETTER_EXCHANGE, exchange_type=_TOPIC, durable=True)
    channel.queue_declare(EDITAL_NOVO_DLQ, durable=True)
    channel.queue_bind(EDITAL_NOVO_DLQ, DEAD_LETTER_EXCHANGE, routing_key=EDITAL_NOVO)
    channel.queue_declare(
        EDITAL_NOVO,
        durable=True,
        arguments={
            "x-dead-letter-exchange": DEAD_LETTER_EXCHANGE,
            "x-dead-letter-routing-key": EDITAL_NOVO,
        },
    )
    channel.queue_bind(EDITAL_NOVO, EXCHANGE, routing_key=EDITAL_NOVO)


class RabbitMqPublisher:
    """Publica com *publisher confirms*: só retorna quando o broker garante que guardou."""

    def __init__(self, parameters: pika.ConnectionParameters) -> None:
        self._parameters = parameters
        self._connection: pika.BlockingConnection | None = None
        self._channel: BlockingChannel | None = None

    def publish(self, event: EditalNovoV1) -> None:
        properties = pika.BasicProperties(
            content_type="application/json",
            delivery_mode=PERSISTENT_DELIVERY_MODE,  # 2 = gravada em disco pelo broker
            message_id=str(event.event_id),  # o consumidor usa para ignorar duplicatas
            type=event.event_type,
            headers={"schema_version": event.schema_version},
        )
        try:
            self._ensure_channel().basic_publish(
                exchange=EXCHANGE,
                routing_key=EDITAL_NOVO,
                body=event.model_dump_json().encode("utf-8"),
                properties=properties,
                mandatory=True,  # sem fila para receber = erro, e não descarte silencioso
            )
        except AMQPError as exc:
            self.close()  # conexão possivelmente quebrada: a próxima chamada reconecta
            raise PublishError(f"falha ao publicar {event.event_id}: {exc!r}") from exc

    def close(self) -> None:
        if self._connection is not None and self._connection.is_open:
            try:
                self._connection.close()
            except AMQPError as exc:
                log.warning("rabbitmq_close_falhou", erro=repr(exc))
        self._connection = None
        self._channel = None

    def _ensure_channel(self) -> BlockingChannel:
        if self._channel is None or self._channel.is_closed:
            self._connection = pika.BlockingConnection(self._parameters)
            channel = self._connection.channel()
            channel.confirm_delivery()  # liga os publisher confirms neste canal
            declare_topology(channel)
            self._channel = channel
        return self._channel


def connection_parameters(
    host: str, port: int, user: str, password: str
) -> pika.ConnectionParameters:
    return pika.ConnectionParameters(
        host=host,
        port=port,
        credentials=pika.PlainCredentials(user, password),
        heartbeat=60,
        blocked_connection_timeout=30,
        connection_attempts=3,
        retry_delay=2,
    )
