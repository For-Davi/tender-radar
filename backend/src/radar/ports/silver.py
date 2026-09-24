"""Portas da camada silver usadas pelo pipeline bronze -> silver.

Além dos repositórios das entidades (`ports/repositories.py`), o pipeline precisa:
- registrar o que foi rejeitado e por quê (qualidade de dados);
- lembrar até onde já processou (marca d'água, processamento incremental);
- controlar a transação (`commit`/`rollback`) sem saber que é SQLAlchemy.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from radar.ports.repositories import (
    ContratacaoRepository,
    FornecedorRepository,
    OrgaoRepository,
)


class MotivoRejeicao(StrEnum):
    # formato/completude: campo ausente, tipo errado, valor que não se converte
    CAMPO_INVALIDO = "campo_invalido"
    # valor bem formado que viola uma regra do domínio (ex.: quantidade <= 0)
    REGRA_NEGOCIO = "regra_negocio"
    # unicidade: o mesmo número de item aparece duas vezes na contratação
    ITEM_DUPLICADO = "item_duplicado"
    # o resultado (vencedor) do item não pôde ser lido (fornecedor ou preço inválido)
    RESULTADO_INVALIDO = "resultado_invalido"
    # o banco recusou o registro (não deveria acontecer: indica bug de validação)
    PERSISTENCIA = "persistencia"


@dataclass(frozen=True, slots=True)
class Problema:
    campo: str  # caminho do campo no bruto, ex.: "contratacao.orgaoEntidade.cnpj"
    erro: str


@dataclass(frozen=True, slots=True)
class Rejeicao:
    """Uma contratação (numero_item=None) ou um item rejeitado, com o motivo."""

    numero_controle_pncp: str
    bronze_hash: str  # qual versão da bronze foi rejeitada (linhagem)
    motivo: MotivoRejeicao
    problemas: tuple[Problema, ...]
    numero_item: int | None = None


class RejeicaoRepository(Protocol):
    def add(self, rejeicao: Rejeicao) -> None:
        """Registra a rejeição. Idempotente: a mesma versão/item não é registrada 2x."""
        ...


class WatermarkRepository(Protocol):
    def get(self, pipeline: str) -> datetime | None: ...
    def set(self, pipeline: str, marca: datetime) -> None: ...


class SilverUnitOfWork(Protocol):
    """Os repositórios da silver numa mesma transação.

    Propriedades (somente leitura) em vez de atributos: assim qualquer classe que
    devolva um repositório compatível satisfaz o protocolo.
    """

    @property
    def orgaos(self) -> OrgaoRepository: ...
    @property
    def fornecedores(self) -> FornecedorRepository: ...
    @property
    def contratacoes(self) -> ContratacaoRepository: ...
    @property
    def rejeicoes(self) -> RejeicaoRepository: ...
    @property
    def watermarks(self) -> WatermarkRepository: ...

    def commit(self) -> None: ...
    def rollback(self) -> None: ...
