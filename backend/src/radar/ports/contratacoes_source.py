"""Porta da fonte de contratações (implementada pelo cliente do PNCP).

O serviço de ingestão depende só disto. Os tipos daqui carregam o mínimo que o
serviço precisa saber (chaves, se o item tem resultado, se o documento é edital) e
o `payload` bruto, que vai intacto para a camada bronze.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

# Any: é JSON de uma fonte externa, com dezenas de campos que mudam com o tempo.
# Só os campos essenciais são validados (pelo adapter); o resto é guardado como veio.
JsonDict = dict[str, Any]


class SourceError(Exception):
    """Base dos erros da fonte."""


class SourceUnavailableError(SourceError):
    """A fonte não respondeu a tempo ou falhou (5xx/429) mesmo após as novas tentativas."""


class SourceRequestError(SourceError):
    """A fonte recusou o pedido (4xx): repetir não adianta."""


class SourceSchemaError(SourceError):
    """A resposta não tem o formato esperado (campo obrigatório ausente ou tipo errado)."""


class DocumentTooLargeError(SourceError):
    """O documento passa do tamanho máximo configurado."""


@dataclass(frozen=True, slots=True)
class ContratacaoRef:
    """Identifica uma contratação no PNCP."""

    numero_controle_pncp: str
    cnpj: str
    ano: int
    sequencial: int


@dataclass(frozen=True, slots=True)
class RawContratacao:
    ref: ContratacaoRef
    payload: JsonDict


@dataclass(frozen=True, slots=True)
class RawItem:
    numero_item: int
    tem_resultado: bool
    payload: JsonDict


@dataclass(frozen=True, slots=True)
class DocumentoRef:
    sequencial_documento: int
    eh_edital: bool
    url: str
    payload: JsonDict


class ContratacoesSource(Protocol):
    def list_contratacoes(
        self, data_inicial: date, data_final: date, modalidade: int, uf: str
    ) -> Iterator[RawContratacao]:
        """Todas as contratações publicadas no período (percorre as páginas sozinho)."""
        ...

    def get_itens(self, ref: ContratacaoRef) -> list[RawItem]: ...

    def get_resultados(self, ref: ContratacaoRef, numero_item: int) -> list[JsonDict]: ...

    def get_documentos(self, ref: ContratacaoRef) -> list[DocumentoRef]: ...

    def download(self, url: str) -> bytes:
        """Baixa o arquivo; `DocumentTooLargeError` se passar do limite."""
        ...
