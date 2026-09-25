"""Dependências das rotas (injeção via `Depends` do FastAPI).

Cada requisição ganha a própria sessão do banco (`get_session`), fechada no fim. As
rotas não criam adapters: pedem o port (`ContratacaoQueriesDep`) e recebem a
implementação SQL. Nos testes, `app.dependency_overrides` troca a implementação
por um fake em memória, sem mudar nenhuma linha das rotas.
"""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session, sessionmaker

from radar.adapters.postgres.consultas import SqlContratacaoQueries, SqlOrgaoQueries
from radar.adapters.postgres.gold import SqlMetricasQueries
from radar.ports.consultas import ContratacaoQueries, OrgaoQueries
from radar.ports.metricas import MetricasQueries


def get_session(request: Request) -> Iterator[Session]:
    """Uma sessão por requisição; o `with` fecha (e desfaz a transação) no fim."""
    factory: sessionmaker[Session] = request.app.state.session_factory
    with factory() as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


def get_contratacao_queries(session: SessionDep) -> ContratacaoQueries:
    return SqlContratacaoQueries(session)


def get_orgao_queries(session: SessionDep) -> OrgaoQueries:
    return SqlOrgaoQueries(session)


def get_metricas_queries(session: SessionDep) -> MetricasQueries:
    return SqlMetricasQueries(session)


ContratacaoQueriesDep = Annotated[ContratacaoQueries, Depends(get_contratacao_queries)]
OrgaoQueriesDep = Annotated[OrgaoQueries, Depends(get_orgao_queries)]
MetricasQueriesDep = Annotated[MetricasQueries, Depends(get_metricas_queries)]
