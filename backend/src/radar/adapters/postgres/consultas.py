"""Consultas de leitura na silver (implementam `radar.ports.consultas`).

Usam SQL "Core" (`select` com colunas), e não objetos ORM: a consulta traz só as
colunas de que a tela precisa, já com o join do órgão, e cada linha vira um read
model. Nada é carregado "por acaso" (sem N+1).
"""

from collections.abc import Sequence
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, Row, Select, UnaryExpression, and_, exists, func, select
from sqlalchemy.orm import Session

from radar.adapters.postgres.models import (
    ContratacaoModel,
    FornecedorModel,
    ItemContratacaoModel,
    OrgaoModel,
)
from radar.domain.enums import (
    Esfera,
    MaterialOuServico,
    Modalidade,
    Poder,
    SituacaoContratacao,
    TipoPessoa,
)
from radar.ports.consultas import (
    ContratacaoDetalhe,
    ContratacaoResumo,
    FiltroContratacoes,
    FornecedorRef,
    ItemDetalhe,
    Ordenacao,
    OrgaoRef,
    OrgaoResumo,
    Pagina,
    PaginaPedido,
)

# o "dia" de uma publicação é o dia em Brasília (mesma regra do dbt, stg_contratacao)
BRASILIA = ZoneInfo("America/Sao_Paulo")

C = ContratacaoModel
O = OrgaoModel  # noqa: E741 (nome curto de propósito, como um alias de tabela em SQL)
I = ItemContratacaoModel  # noqa: E741
F = FornecedorModel


def inicio_do_dia(dia: date) -> datetime:
    """00:00 de Brasília daquele dia (vira UTC na comparação com a coluna)."""
    return datetime.combine(dia, time.min, tzinfo=BRASILIA)


def _total_itens() -> Any:
    # subconsulta correlacionada: conta os itens da contratação da linha de fora
    return (
        select(func.count())
        .where(I.contratacao_id == C.id)
        .correlate(C)
        .scalar_subquery()
        .label("total_itens")
    )


def _conditions(filtro: FiltroContratacoes) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    if filtro.uf is not None:
        conditions.append(C.uf == filtro.uf)
    if filtro.orgao_cnpj is not None:
        conditions.append(O.cnpj == filtro.orgao_cnpj)
    if filtro.categoria is not None:
        # EXISTS: a contratação entra se ALGUM item for do capítulo (sem duplicar linhas,
        # o que aconteceria com um JOIN nos itens)
        conditions.append(
            exists().where(I.contratacao_id == C.id, func.left(I.ncm_nbs, 2) == filtro.categoria)
        )
    # intervalo meio-aberto [início do 1º dia, início do dia seguinte ao último):
    # compara a coluna direto (usa o índice) e não perde 23:59:59.999
    if filtro.data_inicio is not None:
        conditions.append(C.data_publicacao >= inicio_do_dia(filtro.data_inicio))
    if filtro.data_fim is not None:
        conditions.append(C.data_publicacao < inicio_do_dia(filtro.data_fim + timedelta(days=1)))
    # valor nulo (sigiloso) nunca satisfaz ">=" nem "<=" em SQL: fica de fora sozinho
    if filtro.valor_min is not None:
        conditions.append(C.valor_total_estimado >= filtro.valor_min)
    if filtro.valor_max is not None:
        conditions.append(C.valor_total_estimado <= filtro.valor_max)
    return conditions


def _order_by(ordenacao: Ordenacao) -> tuple[UnaryExpression[Any], ...]:
    # o id no fim desempata: sem ele, linhas com a mesma data podem trocar de página
    # entre uma requisição e outra (o Postgres não garante ordem entre empatados)
    match ordenacao:
        case Ordenacao.DATA_DESC:
            return (C.data_publicacao.desc(), C.id.desc())
        case Ordenacao.DATA_ASC:
            return (C.data_publicacao.asc(), C.id.asc())
        # sigilosos (nulos) sempre no fim, nos dois sentidos
        case Ordenacao.VALOR_DESC:
            return (C.valor_total_estimado.desc().nulls_last(), C.id.desc())
        case Ordenacao.VALOR_ASC:
            return (C.valor_total_estimado.asc().nulls_last(), C.id.asc())


def _resumo_select() -> Select[Any]:
    return select(
        C.numero_controle_pncp,
        O.cnpj,
        O.razao_social,
        C.modalidade,
        C.situacao,
        C.objeto,
        C.valor_total_estimado,
        C.data_publicacao,
        C.uf,
        C.municipio,
        _total_itens(),
    ).join(O, O.id == C.orgao_id)


def _to_resumo(row: Row[Any]) -> ContratacaoResumo:
    return ContratacaoResumo(
        numero_controle_pncp=row.numero_controle_pncp,
        orgao=OrgaoRef(cnpj=row.cnpj, razao_social=row.razao_social),
        modalidade=Modalidade(row.modalidade),
        situacao=SituacaoContratacao(row.situacao),
        objeto=row.objeto,
        valor_total_estimado=row.valor_total_estimado,
        data_publicacao=row.data_publicacao,
        uf=row.uf,
        municipio=row.municipio,
        total_itens=row.total_itens,
    )


def _to_item(row: Row[Any]) -> ItemDetalhe:
    vencedor = (
        None
        if row.documento is None
        else FornecedorRef(
            documento=row.documento, nome=row.nome, tipo_pessoa=TipoPessoa(row.tipo_pessoa)
        )
    )
    return ItemDetalhe(
        numero_item=row.numero_item,
        descricao=row.descricao,
        material_ou_servico=MaterialOuServico(row.material_ou_servico),
        ncm_nbs=row.ncm_nbs,
        quantidade=row.quantidade,
        unidade_medida=row.unidade_medida,
        valor_unitario_estimado=row.valor_unitario_estimado,
        vencedor=vencedor,
        valor_unitario_homologado=row.valor_unitario_homologado,
    )


class SqlContratacaoQueries:
    def __init__(self, session: Session) -> None:
        self._session = session

    def listar(
        self, filtro: FiltroContratacoes, ordenacao: Ordenacao, pedido: PaginaPedido
    ) -> Pagina[ContratacaoResumo]:
        conditions = _conditions(filtro)
        total_stmt = (
            select(func.count()).select_from(C).join(O, O.id == C.orgao_id).where(*conditions)
        )
        total = self._session.scalar(total_stmt) or 0
        rows = self._session.execute(
            _resumo_select()
            .where(*conditions)
            .order_by(*_order_by(ordenacao))
            .limit(pedido.tamanho)
            .offset(pedido.offset)
        )
        return Pagina([_to_resumo(row) for row in rows], total, pedido)

    def detalhar(self, numero_controle_pncp: str) -> ContratacaoDetalhe | None:
        row = self._session.execute(
            _resumo_select().where(C.numero_controle_pncp == numero_controle_pncp)
        ).one_or_none()
        if row is None:
            return None
        return ContratacaoDetalhe(_to_resumo(row), self._itens(numero_controle_pncp))

    def _itens(self, numero_controle_pncp: str) -> Sequence[ItemDetalhe]:
        rows = self._session.execute(
            select(
                I.numero_item,
                I.descricao,
                I.material_ou_servico,
                I.ncm_nbs,
                I.quantidade,
                I.unidade_medida,
                I.valor_unitario_estimado,
                I.valor_unitario_homologado,
                F.documento,
                F.nome,
                F.tipo_pessoa,
            )
            .join(C, C.id == I.contratacao_id)
            # LEFT JOIN: a maioria dos itens ainda não tem vencedor
            .outerjoin(F, F.id == I.fornecedor_id)
            .where(C.numero_controle_pncp == numero_controle_pncp)
            .order_by(I.numero_item)
        )
        return tuple(_to_item(row) for row in rows)


class SqlOrgaoQueries:
    def __init__(self, session: Session) -> None:
        self._session = session

    def listar(self, uf: str | None, pedido: PaginaPedido) -> Pagina[OrgaoResumo]:
        # a condição da UF fica no JOIN (e não no WHERE) para a contagem ser só da UF
        join_on: list[ColumnElement[bool]] = [C.orgao_id == O.id]
        if uf is not None:
            join_on.append(C.uf == uf)
        total_contratacoes = func.count(C.id).label("total_contratacoes")
        stmt = (
            select(O.cnpj, O.razao_social, O.esfera, O.poder, total_contratacoes)
            .outerjoin(C, and_(*join_on))
            .group_by(O.id)
        )
        if uf is not None:
            # com UF, só órgãos que têm contratação nela
            stmt = stmt.having(func.count(C.id) > 0)
        total = self._session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = self._session.execute(
            stmt.order_by(O.razao_social, O.id).limit(pedido.tamanho).offset(pedido.offset)
        )
        itens = [
            OrgaoResumo(
                cnpj=row.cnpj,
                razao_social=row.razao_social,
                esfera=Esfera(row.esfera),
                poder=Poder(row.poder),
                total_contratacoes=row.total_contratacoes,
            )
            for row in rows
        ]
        return Pagina(itens, total, pedido)
