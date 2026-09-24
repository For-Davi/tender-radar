"""Repositórios SQL: implementam os ports de `radar.ports.repositories` no Postgres.

Cada escrita roda dentro de um SAVEPOINT (`begin_nested`). Se ela falhar, só o
savepoint é desfeito, e a transação de quem chamou continua utilizável (dá para
registrar o erro e seguir com o próximo registro do lote). O commit é de quem chama.
"""

from collections.abc import Iterable, Iterator
from contextlib import contextmanager

from sqlalchemy import delete, func, insert, select
from sqlalchemy.dialects.postgresql import Insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from radar.adapters.postgres.errors import raise_as_domain_error
from radar.adapters.postgres.mappers import (
    Row,
    contratacao_to_domain,
    contratacao_values,
    fornecedor_to_domain,
    fornecedor_values,
    item_values,
    orgao_to_domain,
    orgao_values,
)
from radar.adapters.postgres.models import (
    Base,
    ContratacaoModel,
    FornecedorModel,
    ItemContratacaoModel,
    OrgaoModel,
)
from radar.domain.entities import Contratacao, Fornecedor, Orgao
from radar.domain.errors import ReferenceNotFoundError
from radar.domain.value_objects import Cnpj


def _upsert(model: type[Base], rows: list[Row], conflict_columns: list[str]) -> Insert:
    """INSERT ... ON CONFLICT (chave natural) DO UPDATE: atômico e idempotente.

    `excluded` é a linha que tentou entrar; no conflito, copiamos os valores dela
    para a linha existente (menos a própria chave) e atualizamos `atualizado_em`.
    """
    stmt = pg_insert(model).values(rows)
    updated = {col: stmt.excluded[col] for col in rows[0] if col not in conflict_columns}
    return stmt.on_conflict_do_update(
        index_elements=conflict_columns, set_={**updated, "atualizado_em": func.now()}
    )


# As escritas usam SQL "Core" (INSERT/UPSERT diretos), que não atualizam objetos já
# carregados no identity map da sessão. populate_existing força o SELECT a sobrescrevê-los,
# garantindo que o `get` nunca devolva uma versão antiga que ficou em memória.
_FRESH = {"populate_existing": True}


class _SqlRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    @contextmanager
    def _savepoint(self) -> Iterator[None]:
        try:
            with self._session.begin_nested():
                yield
        except IntegrityError as exc:
            raise_as_domain_error(exc)


class SqlOrgaoRepository(_SqlRepository):
    def add(self, orgao: Orgao) -> None:
        with self._savepoint():
            self._session.execute(insert(OrgaoModel).values(orgao_values(orgao)))

    def upsert(self, orgao: Orgao) -> None:
        with self._savepoint():
            self._session.execute(_upsert(OrgaoModel, [orgao_values(orgao)], ["cnpj"]))

    def get(self, cnpj: Cnpj) -> Orgao | None:
        stmt = select(OrgaoModel).where(OrgaoModel.cnpj == cnpj.value)
        model = self._session.scalar(stmt.execution_options(**_FRESH))
        return None if model is None else orgao_to_domain(model)


class SqlFornecedorRepository(_SqlRepository):
    def add(self, fornecedor: Fornecedor) -> None:
        with self._savepoint():
            self._session.execute(insert(FornecedorModel).values(fornecedor_values(fornecedor)))

    def upsert(self, fornecedor: Fornecedor) -> None:
        with self._savepoint():
            self._session.execute(
                _upsert(FornecedorModel, [fornecedor_values(fornecedor)], ["documento"])
            )

    def get(self, documento: str) -> Fornecedor | None:
        stmt = select(FornecedorModel).where(FornecedorModel.documento == documento)
        model = self._session.scalar(stmt.execution_options(**_FRESH))
        return None if model is None else fornecedor_to_domain(model)


class SqlContratacaoRepository(_SqlRepository):
    """Salva a contratação e seus itens juntos: é tudo ou nada (mesmo savepoint)."""

    def add(self, contratacao: Contratacao) -> None:
        with self._savepoint():
            orgao_id = self._orgao_id(contratacao.orgao_cnpj)
            contratacao_id = self._session.scalars(
                insert(ContratacaoModel)
                .values(contratacao_values(contratacao, orgao_id))
                .returning(ContratacaoModel.id)
            ).one()
            rows = self._item_rows(contratacao, contratacao_id)
            if rows:
                self._session.execute(insert(ItemContratacaoModel).values(rows))

    def upsert(self, contratacao: Contratacao) -> None:
        with self._savepoint():
            orgao_id = self._orgao_id(contratacao.orgao_cnpj)
            stmt = _upsert(
                ContratacaoModel,
                [contratacao_values(contratacao, orgao_id)],
                ["numero_controle_pncp"],
            )
            contratacao_id = self._session.scalars(stmt.returning(ContratacaoModel.id)).one()
            rows = self._item_rows(contratacao, contratacao_id)
            if rows:
                self._session.execute(
                    _upsert(ItemContratacaoModel, rows, ["contratacao_id", "numero_item"])
                )
            # o agregado é a fonte da verdade: itens que saíram da contratação saem do banco
            self._session.execute(
                delete(ItemContratacaoModel).where(
                    ItemContratacaoModel.contratacao_id == contratacao_id,
                    ItemContratacaoModel.numero_item.not_in(
                        [item.numero_item for item in contratacao.itens]
                    ),
                )
            )

    def get(self, numero_controle_pncp: str) -> Contratacao | None:
        stmt = (
            select(ContratacaoModel)
            .where(ContratacaoModel.numero_controle_pncp == numero_controle_pncp)
            # carregamento explícito: 1 consulta para órgão, 1 para itens + fornecedores
            .options(
                joinedload(ContratacaoModel.orgao),
                selectinload(ContratacaoModel.itens).joinedload(ItemContratacaoModel.fornecedor),
            )
            .execution_options(**_FRESH)
        )
        model = self._session.scalar(stmt)
        return None if model is None else contratacao_to_domain(model)

    def _orgao_id(self, cnpj: Cnpj) -> int:
        orgao_id = self._session.scalar(select(OrgaoModel.id).where(OrgaoModel.cnpj == cnpj.value))
        if orgao_id is None:
            raise ReferenceNotFoundError(f"órgão não cadastrado: CNPJ {cnpj.value}")
        return orgao_id

    def _fornecedor_ids(self, documentos: Iterable[str]) -> dict[str, int]:
        wanted = set(documentos)
        if not wanted:
            return {}
        rows = self._session.execute(
            select(FornecedorModel.documento, FornecedorModel.id).where(
                FornecedorModel.documento.in_(wanted)
            )
        )
        found = {documento: id_ for documento, id_ in rows}
        missing = wanted - found.keys()
        if missing:
            raise ReferenceNotFoundError(f"fornecedor(es) não cadastrado(s): {sorted(missing)}")
        return found

    def _item_rows(self, contratacao: Contratacao, contratacao_id: int) -> list[Row]:
        fornecedor_ids = self._fornecedor_ids(
            item.fornecedor_documento for item in contratacao.itens if item.fornecedor_documento
        )
        return [
            item_values(
                item,
                contratacao_id,
                fornecedor_ids[item.fornecedor_documento] if item.fornecedor_documento else None,
            )
            for item in contratacao.itens
        ]
