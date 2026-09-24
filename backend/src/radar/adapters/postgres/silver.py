"""Portas da silver no Postgres: rejeições, marca d'água e a unidade de trabalho."""

from dataclasses import asdict
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from radar.adapters.postgres.models import PipelineWatermarkModel, RegistroRejeitadoModel
from radar.adapters.postgres.repositories import (
    SqlContratacaoRepository,
    SqlFornecedorRepository,
    SqlOrgaoRepository,
    SqlRepository,
)
from radar.ports.silver import Rejeicao

_UNIQUE_REJEICAO = "uq_registros_rejeitados_versao_item"


class SqlRejeicaoRepository(SqlRepository):
    def add(self, rejeicao: Rejeicao) -> None:
        stmt = (
            pg_insert(RegistroRejeitadoModel)
            .values(
                numero_controle_pncp=rejeicao.numero_controle_pncp,
                bronze_hash=rejeicao.bronze_hash,
                numero_item=rejeicao.numero_item,
                motivo=rejeicao.motivo.value,
                detalhes=[asdict(problema) for problema in rejeicao.problemas],
            )
            # a mesma versão/item já rejeitada (reprocessamento): não faz nada
            .on_conflict_do_nothing(constraint=_UNIQUE_REJEICAO)
        )
        with self._savepoint():
            self._session.execute(stmt)


class SqlWatermarkRepository(SqlRepository):
    def get(self, pipeline: str) -> datetime | None:
        return self._session.scalar(
            select(PipelineWatermarkModel.marca).where(PipelineWatermarkModel.pipeline == pipeline)
        )

    def set(self, pipeline: str, marca: datetime) -> None:
        stmt = pg_insert(PipelineWatermarkModel).values(pipeline=pipeline, marca=marca)
        stmt = stmt.on_conflict_do_update(
            index_elements=["pipeline"],
            set_={"marca": stmt.excluded.marca, "atualizado_em": func.now()},
        )
        with self._savepoint():
            self._session.execute(stmt)


class SqlSilverUnitOfWork:
    """Todos os repositórios da silver sobre a MESMA sessão (= mesma transação)."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._orgaos = SqlOrgaoRepository(session)
        self._fornecedores = SqlFornecedorRepository(session)
        self._contratacoes = SqlContratacaoRepository(session)
        self._rejeicoes = SqlRejeicaoRepository(session)
        self._watermarks = SqlWatermarkRepository(session)

    @property
    def orgaos(self) -> SqlOrgaoRepository:
        return self._orgaos

    @property
    def fornecedores(self) -> SqlFornecedorRepository:
        return self._fornecedores

    @property
    def contratacoes(self) -> SqlContratacaoRepository:
        return self._contratacoes

    @property
    def rejeicoes(self) -> SqlRejeicaoRepository:
        return self._rejeicoes

    @property
    def watermarks(self) -> SqlWatermarkRepository:
        return self._watermarks

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()
