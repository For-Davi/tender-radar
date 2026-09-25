"""Porta de leitura da camada gold (marts do dbt, Etapa 04).

A gold é construída pelo dbt, e não pelas migrações do backend. Ela pode não existir
(o `make dbt` ainda não rodou) ou estar sendo reconstruída. Nesses casos o adapter
levanta `AnaliticoIndisponivelError`, e a API responde 503 (tente mais tarde), não 500.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol

from radar.domain.enums import MaterialOuServico
from radar.ports.consultas import Pagina, PaginaPedido


class AnaliticoIndisponivelError(Exception):
    """As tabelas da gold não existem (o dbt ainda não rodou neste banco)."""


@dataclass(frozen=True, slots=True, kw_only=True)
class Categoria:
    material_ou_servico: MaterialOuServico
    ncm_capitulo: str | None  # None = "sem classificação"
    nome: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ValorMensal:
    mes: date
    contratacoes: int
    itens: int
    valor_total_estimado: Decimal
    media_movel_3m: Decimal
    meses_na_media: int


@dataclass(frozen=True, slots=True, kw_only=True)
class PrecoCategoriaMensal:
    categoria: Categoria
    unidade: str
    mes: date
    itens: int
    preco_medio: Decimal
    preco_mediano: Decimal
    preco_mediano_mes_anterior: Decimal | None
    variacao_percentual: Decimal | None


@dataclass(frozen=True, slots=True, kw_only=True)
class RankingFornecedor:
    orgao_cnpj: str
    orgao_razao_social: str
    fornecedor_documento: str
    fornecedor_nome: str
    itens_vencidos: int
    valor_total_homologado: Decimal
    ranking: int
    participacao_percentual: Decimal | None


@dataclass(frozen=True, slots=True, kw_only=True)
class PrecoAcimaP90:
    numero_controle_pncp: str
    numero_item: int
    orgao_razao_social: str
    categoria_nome: str
    unidade: str
    data_publicacao: date
    valor_unitario_estimado: Decimal
    percentil_preco: Decimal
    itens_comparaveis: int


class MetricasQueries(Protocol):
    def categorias(self) -> Sequence[Categoria]: ...

    def valor_mensal(self) -> Sequence[ValorMensal]: ...

    def preco_categoria(self, ncm_capitulo: str | None) -> Sequence[PrecoCategoriaMensal]: ...

    def ranking_fornecedores(self, orgao_cnpj: str | None) -> Sequence[RankingFornecedor]: ...

    def precos_acima_p90(self, pedido: PaginaPedido) -> Pagina[PrecoAcimaP90]: ...
