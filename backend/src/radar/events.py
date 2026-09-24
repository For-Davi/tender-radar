"""Contratos dos eventos trocados entre os processos (via RabbitMQ).

Um evento é um fato que já aconteceu ("um edital novo foi baixado"), no passado.
Cada tipo tem versão no nome (`V1`) e no corpo (`schema_version`): para mudar o
formato, cria-se um `V2` e os consumidores migram sem pressa. Nunca se altera um
evento já publicado.
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

# Namespace fixo: o mesmo documento sempre gera o mesmo event_id (ver `for_document`)
_EVENT_NAMESPACE = uuid.UUID("5b4f6d3e-7a1c-4e2b-9f0a-3c8d2e1b6a70")


class EditalNovoV1(BaseModel):
    """Um documento de edital foi baixado e está pronto para ser lido (Etapa 07)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: uuid.UUID
    event_type: Literal["edital.novo"] = "edital.novo"
    schema_version: Literal[1] = 1
    occurred_at: AwareDatetime
    numero_controle_pncp: str = Field(min_length=1)
    sequencial_documento: int = Field(ge=1)
    caminho: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @classmethod
    def for_document(
        cls,
        *,
        numero_controle_pncp: str,
        sequencial_documento: int,
        caminho: str,
        sha256: str,
        occurred_at: datetime,
    ) -> "EditalNovoV1":
        """Cria o evento com `event_id` determinístico (UUID v5 do documento).

        Se o mesmo documento for publicado de novo (entrega at-least-once), o
        consumidor recebe o mesmo `event_id` e consegue ignorar a duplicata.
        """
        key = f"{numero_controle_pncp}:{sequencial_documento}:{sha256}"
        return cls(
            event_id=uuid.uuid5(_EVENT_NAMESPACE, key),
            occurred_at=occurred_at,
            numero_controle_pncp=numero_controle_pncp,
            sequencial_documento=sequencial_documento,
            caminho=caminho,
            sha256=sha256,
        )
