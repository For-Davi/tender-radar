"""Porta de publicação de eventos (implementada pelo RabbitMQ)."""

from typing import Protocol

from radar.events import EditalNovoV1


class PublishError(Exception):
    """O broker não confirmou a mensagem: ela pode não ter sido entregue."""


class EventPublisher(Protocol):
    def publish(self, event: EditalNovoV1) -> None:
        """Só retorna depois da confirmação do broker; senão levanta `PublishError`."""
        ...
