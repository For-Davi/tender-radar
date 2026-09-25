"""Portas de LEITURA da silver: o que a API precisa para listar e detalhar.

Os repositórios de `ports/repositories.py` gravam e leem o agregado inteiro (a
entidade de domínio). Para as telas, isso é pouco e é muito ao mesmo tempo:
- pouco: a entidade `Contratacao` não tem o nome do órgão, nem o do fornecedor;
- muito: listar 20 contratações carregaria todos os itens de cada uma.

Por isso a leitura tem contratos próprios, que devolvem *read models*: dataclasses
imutáveis com exatamente o que a consulta precisa. É a ideia do CQRS (separar o
modelo de escrita do de leitura), numa versão leve: o mesmo banco, modelos
diferentes.

Os valores chegam aqui já validados pela borda (a API). Os adapters confiam neles.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from radar.domain.enums import (
    Esfera,
    MaterialOuServico,
    Modalidade,
    Poder,
    SituacaoContratacao,
    TipoPessoa,
)
from radar.domain.value_objects import Dinheiro

TAMANHO_PAGINA_MAXIMO = 100

# ------------------------------------------------------------------ paginação


@dataclass(frozen=True, slots=True)
class PaginaPedido:
    """Qual página o cliente quer (1 = primeira) e quantos itens por página."""

    pagina: int = 1
    tamanho: int = 20

    def __post_init__(self) -> None:
        if self.pagina < 1:
            raise ValueError(f"pagina deve ser >= 1: {self.pagina}")
        if not 1 <= self.tamanho <= TAMANHO_PAGINA_MAXIMO:
            raise ValueError(f"tamanho deve estar entre 1 e {TAMANHO_PAGINA_MAXIMO}")

    @property
    def offset(self) -> int:
        """Quantas linhas pular: a página 3 com tamanho 20 começa na linha 41."""
        return (self.pagina - 1) * self.tamanho


@dataclass(frozen=True, slots=True)
class Pagina[T]:
    """Uma página de resultados e o total de registros que atendem ao filtro."""

    itens: Sequence[T]
    total: int
    pedido: PaginaPedido

    @property
    def total_paginas(self) -> int:
        # divisão arredondando para cima sem float: 41 itens / 20 = 3 páginas
        return -(-self.total // self.pedido.tamanho)


# ------------------------------------------------------------------ filtros


class Ordenacao(StrEnum):
    """Ordenações aceitas. O `-` na frente é decrescente (convenção comum em APIs)."""

    DATA_DESC = "-data_publicacao"
    DATA_ASC = "data_publicacao"
    VALOR_DESC = "-valor_total_estimado"
    VALOR_ASC = "valor_total_estimado"


@dataclass(frozen=True, slots=True, kw_only=True)
class FiltroContratacoes:
    """Filtros combináveis (todos opcionais; `None` = não filtra).

    - `orgao_cnpj`: CNPJ só com dígitos/letras, sem máscara.
    - `categoria`: capítulo NCM/NBS (2 dígitos), a mesma regra do dbt (`stg_item`):
      a contratação entra se ao menos um item for do capítulo.
    - `data_inicio`/`data_fim`: dias de Brasília, ambos inclusivos.
    - `valor_min`/`valor_max`: valor total estimado; valor sigiloso (nulo) nunca entra.
    """

    uf: str | None = None
    orgao_cnpj: str | None = None
    categoria: str | None = None
    data_inicio: date | None = None
    data_fim: date | None = None
    valor_min: Decimal | None = None
    valor_max: Decimal | None = None


# ------------------------------------------------------------------ read models


@dataclass(frozen=True, slots=True)
class OrgaoRef:
    cnpj: str
    razao_social: str


@dataclass(frozen=True, slots=True)
class FornecedorRef:
    documento: str
    nome: str
    tipo_pessoa: TipoPessoa


@dataclass(frozen=True, slots=True, kw_only=True)
class ContratacaoResumo:
    """Uma linha da lista de contratações."""

    numero_controle_pncp: str
    orgao: OrgaoRef
    modalidade: Modalidade
    situacao: SituacaoContratacao
    objeto: str
    valor_total_estimado: Decimal | None  # None = sigiloso
    data_publicacao: datetime
    uf: str
    municipio: str
    total_itens: int


@dataclass(frozen=True, slots=True, kw_only=True)
class ItemDetalhe:
    numero_item: int
    descricao: str
    material_ou_servico: MaterialOuServico
    ncm_nbs: str | None
    quantidade: Decimal
    unidade_medida: str
    valor_unitario_estimado: Decimal | None
    vencedor: FornecedorRef | None
    valor_unitario_homologado: Decimal | None

    @property
    def valor_total_estimado(self) -> Decimal | None:
        """Calculado (como na entidade): desconhecido se o preço for sigiloso.

        Passa pelo  para ter 4 casas: 4999.9000 x 10.0000 daria 8 casas.
        """
        if self.valor_unitario_estimado is None:
            return None
        return (Dinheiro(self.valor_unitario_estimado) * self.quantidade).valor


@dataclass(frozen=True, slots=True)
class ContratacaoDetalhe:
    resumo: ContratacaoResumo
    itens: Sequence[ItemDetalhe]


@dataclass(frozen=True, slots=True, kw_only=True)
class OrgaoResumo:
    cnpj: str
    razao_social: str
    esfera: Esfera
    poder: Poder
    total_contratacoes: int


# ------------------------------------------------------------------ contratos


class ContratacaoQueries(Protocol):
    def listar(
        self, filtro: FiltroContratacoes, ordenacao: Ordenacao, pedido: PaginaPedido
    ) -> Pagina[ContratacaoResumo]: ...

    def detalhar(self, numero_controle_pncp: str) -> ContratacaoDetalhe | None: ...


class OrgaoQueries(Protocol):
    def listar(self, uf: str | None, pedido: PaginaPedido) -> Pagina[OrgaoResumo]:
        """Órgãos em ordem alfabética. Com `uf`, só os que têm contratação na UF,
        e `total_contratacoes` conta só as dessa UF."""
        ...
