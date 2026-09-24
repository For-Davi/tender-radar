"""Porta da camada bronze: dado bruto versionado + registro dos documentos baixados.

O registro de documentos também funciona como *outbox*: um documento baixado nasce
"pendente de evento" e só é marcado como publicado depois que o broker confirma.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from radar.ports.contratacoes_source import JsonDict


@dataclass(frozen=True, slots=True)
class BronzeRecord:
    numero_controle_pncp: str
    payload: JsonDict
    hash: str  # SHA-256 do payload canônico: identifica a versão do conteúdo
    coletado_em: datetime
    fonte: str = "pncp"


@dataclass(frozen=True, slots=True)
class StoredDocument:
    numero_controle_pncp: str
    sequencial_documento: int
    caminho: str  # relativo à raiz do storage
    sha256: str
    tamanho_bytes: int
    tipo_arquivo: str  # "pdf", "zip" ou "desconhecido"
    baixado_em: datetime


@dataclass(frozen=True, slots=True)
class BronzeVersion:
    """Uma versão (conteúdo distinto) de uma contratação, como lida pelo pipeline."""

    numero_controle_pncp: str
    hash: str
    payload: JsonDict
    vigente_desde: datetime  # quando este conteúdo passou a ser a versão atual


class BronzeReader(Protocol):
    def versions_between(
        self, depois_de: datetime | None, ate: datetime
    ) -> Iterator[BronzeVersion]:
        """Versões que viraram a atual em (depois_de, ate], da mais antiga para a mais nova.

        `depois_de=None` = desde o início (reprocessamento completo).
        """
        ...


class BronzeRepository(Protocol):
    def save_if_changed(self, record: BronzeRecord) -> bool:
        """Grava uma nova versão se o conteúdo mudou. Devolve True se gravou."""
        ...

    def document_exists(self, numero_controle_pncp: str, sequencial_documento: int) -> bool: ...

    def register_document(self, document: StoredDocument) -> None:
        """Registra o documento como pendente de evento (idempotente)."""
        ...

    def pending_documents(self) -> list[StoredDocument]:
        """Documentos cujo evento ainda não foi confirmado pelo broker."""
        ...

    def mark_published(
        self, numero_controle_pncp: str, sequencial_documento: int, publicado_em: datetime
    ) -> None: ...
