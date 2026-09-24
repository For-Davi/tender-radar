"""Porta do armazenamento de arquivos (hoje: volume local; amanhã: S3, se precisar)."""

from typing import Protocol


class StorageError(Exception):
    """Falha ao gravar o arquivo (ou chave inválida)."""


class DocumentStorage(Protocol):
    def save(self, key: str, content: bytes) -> str:
        """Grava `content` em `key` (ex.: "cnpj/2025/173/1.pdf") e devolve a chave gravada.

        Gravar de novo a mesma chave substitui o arquivo (idempotente).
        """
        ...
