"""Leitura da camada gold (tabelas criadas pelo dbt, Etapa 04).

Quem cria e altera estas tabelas é o dbt, e NÃO o Alembic: por isso elas ficam num
`MetaData` próprio, fora do `Base` das migrações. As definições abaixo servem para:

1. escrever as consultas com o SQLAlchemy (nomes de coluna checados pelo Python);
2. documentar o CONTRATO entre o dbt e a API: só as colunas que a API usa;
3. criar tabelas equivalentes nos testes de integração (`GOLD_METADATA.create_all`).

O risco é o dbt mudar uma coluna e esta definição não acompanhar. O teste de
contrato (`tests/contract/`) roda no CI depois do `dbt build` e compara esta
definição com as tabelas reais.
"""

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    Integer,
    MetaData,
    Numeric,
    Row,
    String,
    Table,
    Text,
    func,
    select,
)
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from radar.domain.enums import MaterialOuServico
from radar.domain.value_objects import Dinheiro
from radar.ports.consultas import Pagina, PaginaPedido
from radar.ports.metricas import (
    AnaliticoIndisponivelError,
    Categoria,
    PrecoAcimaP90,
    PrecoCategoriaMensal,
    RankingFornecedor,
    ValorMensal,
)

GOLD_SCHEMA = "gold"
GOLD_METADATA = MetaData(schema=GOLD_SCHEMA)

# SQLSTATE do Postgres: tabela não existe / schema não existe
UNDEFINED_TABLE = "42P01"
INVALID_SCHEMA_NAME = "3F000"

dim_orgao = Table(
    "dim_orgao",
    GOLD_METADATA,
    Column("orgao_key", Text, primary_key=True),
    Column("cnpj", String(14)),
    Column("razao_social", Text),
)

dim_fornecedor = Table(
    "dim_fornecedor",
    GOLD_METADATA,
    Column("fornecedor_key", Text, primary_key=True),
    Column("documento", String(30)),
    Column("nome", Text),
)

dim_categoria = Table(
    "dim_categoria",
    GOLD_METADATA,
    Column("categoria_key", Text, primary_key=True),
    Column("material_ou_servico", String(1)),
    Column("ncm_capitulo", Text),
    Column("categoria_nome", Text),
)

mart_valor_contratado_mensal = Table(
    "mart_valor_contratado_mensal",
    GOLD_METADATA,
    Column("mes", Date, primary_key=True),
    Column("contratacoes", BigInteger),
    Column("itens", BigInteger),
    Column("valor_total_estimado", Numeric),
    Column("media_movel_3m", Numeric),
    Column("meses_na_media", BigInteger),
)

mart_preco_categoria_mensal = Table(
    "mart_preco_categoria_mensal",
    GOLD_METADATA,
    Column("categoria_key", Text),
    Column("unidade_normalizada", Text),
    Column("mes", Date),
    Column("itens", BigInteger),
    Column("preco_medio", Numeric),
    Column("preco_mediano", Numeric(18, 4)),
    Column("preco_mediano_mes_anterior", Numeric(18, 4)),
    Column("variacao_percentual", Numeric),
)

mart_ranking_fornecedor_orgao = Table(
    "mart_ranking_fornecedor_orgao",
    GOLD_METADATA,
    Column("orgao_key", Text),
    Column("fornecedor_key", Text),
    Column("itens_vencidos", BigInteger),
    Column("valor_total_homologado", Numeric),
    Column("ranking", BigInteger),
    Column("participacao_percentual", Numeric),
)

mart_percentil_preco_item = Table(
    "mart_percentil_preco_item",
    GOLD_METADATA,
    Column("item_key", Text, primary_key=True),
    Column("numero_controle_pncp", String(30)),
    Column("numero_item", Integer),
    Column("orgao_key", Text),
    Column("categoria_key", Text),
    Column("unidade_normalizada", Text),
    Column("data_publicacao", Date),
    Column("valor_unitario_estimado", Numeric(18, 4)),
    Column("percentil_preco", Numeric),
    Column("itens_comparaveis", BigInteger),
    Column("acima_p90", Boolean),
)


@contextmanager
def _gold_disponivel() -> Iterator[None]:
    """Traduz "tabela/schema não existe" para o erro do port (a API responde 503)."""
    try:
        yield
    except ProgrammingError as exc:
        if getattr(exc.orig, "sqlstate", None) in (UNDEFINED_TABLE, INVALID_SCHEMA_NAME):
            raise AnaliticoIndisponivelError(str(exc.orig)) from exc
        raise


def _dinheiro(valor: Decimal) -> Decimal:
    """Somas de `quantidade x preço` no dbt saem com 8 casas; a API usa sempre 4."""
    return Dinheiro(valor).valor


def _to_categoria(row: Row[Any]) -> Categoria:
    return Categoria(
        material_ou_servico=MaterialOuServico(row.material_ou_servico),
        ncm_capitulo=row.ncm_capitulo,
        nome=row.categoria_nome,
    )


class SqlMetricasQueries:
    def __init__(self, session: Session) -> None:
        self._session = session

    def _fetch[T](self, stmt: Any, convert: Callable[[Row[Any]], T]) -> list[T]:
        with _gold_disponivel():
            return [convert(row) for row in self._session.execute(stmt)]

    def categorias(self) -> Sequence[Categoria]:
        cat = dim_categoria.c
        stmt = select(cat.material_ou_servico, cat.ncm_capitulo, cat.categoria_nome).order_by(
            cat.material_ou_servico, cat.ncm_capitulo.nulls_first()
        )
        return self._fetch(stmt, _to_categoria)

    def valor_mensal(self) -> Sequence[ValorMensal]:
        mart = mart_valor_contratado_mensal.c
        stmt = select(mart_valor_contratado_mensal).order_by(mart.mes)
        return self._fetch(
            stmt,
            lambda row: ValorMensal(
                mes=row.mes,
                contratacoes=row.contratacoes,
                itens=row.itens,
                valor_total_estimado=_dinheiro(row.valor_total_estimado),
                media_movel_3m=row.media_movel_3m,
                meses_na_media=row.meses_na_media,
            ),
        )

    def preco_categoria(self, ncm_capitulo: str | None) -> Sequence[PrecoCategoriaMensal]:
        mart, cat = mart_preco_categoria_mensal.c, dim_categoria.c
        stmt = (
            select(
                mart_preco_categoria_mensal,
                cat.material_ou_servico,
                cat.ncm_capitulo,
                cat.categoria_nome,
            )
            .join(dim_categoria, cat.categoria_key == mart.categoria_key)
            .order_by(cat.categoria_nome, mart.unidade_normalizada, mart.mes)
        )
        if ncm_capitulo is not None:
            stmt = stmt.where(cat.ncm_capitulo == ncm_capitulo)
        return self._fetch(
            stmt,
            lambda row: PrecoCategoriaMensal(
                categoria=_to_categoria(row),
                unidade=row.unidade_normalizada,
                mes=row.mes,
                itens=row.itens,
                preco_medio=row.preco_medio,
                preco_mediano=row.preco_mediano,
                preco_mediano_mes_anterior=row.preco_mediano_mes_anterior,
                variacao_percentual=row.variacao_percentual,
            ),
        )

    def ranking_fornecedores(self, orgao_cnpj: str | None) -> Sequence[RankingFornecedor]:
        mart, org, forn = (
            mart_ranking_fornecedor_orgao.c,
            dim_orgao.c,
            dim_fornecedor.c,
        )
        stmt = (
            select(
                mart_ranking_fornecedor_orgao,
                org.cnpj,
                org.razao_social,
                forn.documento,
                forn.nome,
            )
            .join(dim_orgao, org.orgao_key == mart.orgao_key)
            .join(dim_fornecedor, forn.fornecedor_key == mart.fornecedor_key)
            .order_by(org.razao_social, mart.ranking, forn.nome)
        )
        if orgao_cnpj is not None:
            stmt = stmt.where(org.cnpj == orgao_cnpj)
        return self._fetch(
            stmt,
            lambda row: RankingFornecedor(
                orgao_cnpj=row.cnpj,
                orgao_razao_social=row.razao_social,
                fornecedor_documento=row.documento,
                fornecedor_nome=row.nome,
                itens_vencidos=row.itens_vencidos,
                valor_total_homologado=_dinheiro(row.valor_total_homologado),
                ranking=row.ranking,
                participacao_percentual=row.participacao_percentual,
            ),
        )

    def precos_acima_p90(self, pedido: PaginaPedido) -> Pagina[PrecoAcimaP90]:
        mart, org, cat = mart_percentil_preco_item.c, dim_orgao.c, dim_categoria.c
        alerta = mart.acima_p90.is_(True)
        stmt = (
            select(mart_percentil_preco_item, org.razao_social, cat.categoria_nome)
            .join(dim_orgao, org.orgao_key == mart.orgao_key)
            .join(dim_categoria, cat.categoria_key == mart.categoria_key)
            .where(alerta)
            .order_by(mart.valor_unitario_estimado.desc(), mart.item_key)
            .limit(pedido.tamanho)
            .offset(pedido.offset)
        )
        with _gold_disponivel():
            total = self._session.scalar(
                select(func.count()).select_from(mart_percentil_preco_item).where(alerta)
            )
        itens = self._fetch(
            stmt,
            lambda row: PrecoAcimaP90(
                numero_controle_pncp=row.numero_controle_pncp,
                numero_item=row.numero_item,
                orgao_razao_social=row.razao_social,
                categoria_nome=row.categoria_nome,
                unidade=row.unidade_normalizada,
                data_publicacao=row.data_publicacao,
                valor_unitario_estimado=row.valor_unitario_estimado,
                percentil_preco=row.percentil_preco,
                itens_comparaveis=row.itens_comparaveis,
            ),
        )
        return Pagina(itens, total or 0, pedido)
