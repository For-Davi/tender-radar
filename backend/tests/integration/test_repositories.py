"""Testes dos repositórios SQL contra um Postgres real."""

from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from radar.adapters.postgres.models import Base, ContratacaoModel, ItemContratacaoModel, OrgaoModel
from radar.adapters.postgres.repositories import (
    SqlContratacaoRepository,
    SqlFornecedorRepository,
    SqlOrgaoRepository,
)
from radar.domain.entities import Contratacao
from radar.domain.enums import SituacaoContratacao, TipoPessoa
from radar.domain.errors import DuplicateEntityError, ReferenceNotFoundError
from radar.domain.value_objects import Cnpj, Dinheiro
from tests.factories import (
    CNPJ_FORNECEDOR,
    CNPJ_ORGAO,
    make_contratacao,
    make_fornecedor,
    make_item,
    make_orgao,
)


def _count(session: Session, model: type[Base]) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def _contratacao_com_resultado() -> Contratacao:
    return make_contratacao(
        itens=[
            make_item(numero_item=1, quantidade=Decimal("2.5")),
            make_item(
                numero_item=2,
                valor_unitario_estimado=Dinheiro.de("0.0345"),
                fornecedor_documento=CNPJ_FORNECEDOR,
                valor_unitario_homologado=Dinheiro.de("0.0301"),
            ),
        ]
    )


@pytest.fixture
def cadastros(session: Session) -> Session:
    """Órgão e fornecedor já gravados (pré-requisito das contratações)."""
    SqlOrgaoRepository(session).add(make_orgao())
    SqlFornecedorRepository(session).add(make_fornecedor())
    session.commit()
    return session


# ------------------------------------------------------------------ Orgao


def test_orgao_add_and_get(session: Session) -> None:
    repo = SqlOrgaoRepository(session)
    repo.add(make_orgao())
    session.commit()

    assert repo.get(Cnpj(CNPJ_ORGAO)) == make_orgao()


def test_orgao_get_missing_returns_none(session: Session) -> None:
    assert SqlOrgaoRepository(session).get(Cnpj(CNPJ_ORGAO)) is None


def test_orgao_add_duplicate_raises_domain_error(session: Session) -> None:
    repo = SqlOrgaoRepository(session)
    repo.add(make_orgao())

    with pytest.raises(DuplicateEntityError):
        repo.add(make_orgao(razao_social="Outro nome, mesmo CNPJ"))


def test_session_still_usable_after_domain_error(session: Session) -> None:
    # o savepoint desfaz só a escrita que falhou; a transação continua viva
    repo = SqlOrgaoRepository(session)
    repo.add(make_orgao())
    with pytest.raises(DuplicateEntityError):
        repo.add(make_orgao())

    repo.add(make_orgao(cnpj=Cnpj("12ABC34501DE35")))
    session.commit()

    assert _count(session, OrgaoModel) == 2


def test_orgao_upsert_is_idempotent_and_updates(session: Session) -> None:
    repo = SqlOrgaoRepository(session)
    repo.upsert(make_orgao(razao_social="Nome antigo"))
    repo.upsert(make_orgao(razao_social="Nome novo"))
    session.commit()

    assert _count(session, OrgaoModel) == 1
    orgao = repo.get(Cnpj(CNPJ_ORGAO))
    assert orgao is not None
    assert orgao.razao_social == "Nome novo"


# ------------------------------------------------------------------ Fornecedor


@pytest.mark.parametrize(
    ("tipo", "documento"),
    [(TipoPessoa.JURIDICA, CNPJ_FORNECEDOR), (TipoPessoa.FISICA, "52998224725")],
)
def test_fornecedor_add_and_get(session: Session, tipo: TipoPessoa, documento: str) -> None:
    repo = SqlFornecedorRepository(session)
    fornecedor = make_fornecedor(tipo_pessoa=tipo, documento=documento)
    repo.add(fornecedor)
    session.commit()

    assert repo.get(fornecedor.documento) == fornecedor


def test_fornecedor_upsert_does_not_duplicate(session: Session) -> None:
    repo = SqlFornecedorRepository(session)
    repo.upsert(make_fornecedor(nome="A"))
    repo.upsert(make_fornecedor(nome="B"))
    session.commit()

    fornecedor = repo.get(CNPJ_FORNECEDOR)
    assert fornecedor is not None
    assert fornecedor.nome == "B"


def test_fornecedor_add_duplicate_raises_domain_error(session: Session) -> None:
    repo = SqlFornecedorRepository(session)
    repo.add(make_fornecedor())

    with pytest.raises(DuplicateEntityError):
        repo.add(make_fornecedor())


# ------------------------------------------------------------------ Contratacao


def test_contratacao_add_and_get_roundtrip(cadastros: Session) -> None:
    repo = SqlContratacaoRepository(cadastros)
    contratacao = _contratacao_com_resultado()
    repo.add(contratacao)
    cadastros.commit()

    loaded = repo.get(contratacao.numero_controle_pncp)

    # igualdade campo a campo, incluindo itens, Decimal exato e fornecedor do resultado
    assert loaded == contratacao


def test_contratacao_get_missing_returns_none(session: Session) -> None:
    assert SqlContratacaoRepository(session).get("11222333000181-1-999999/2025") is None


def test_contratacao_with_unknown_orgao_raises_reference_error(session: Session) -> None:
    with pytest.raises(ReferenceNotFoundError, match="órgão"):
        SqlContratacaoRepository(session).add(make_contratacao())


def test_item_with_unknown_fornecedor_saves_nothing(cadastros: Session) -> None:
    repo = SqlContratacaoRepository(cadastros)
    contratacao = make_contratacao(
        itens=[
            make_item(numero_item=1),
            make_item(
                numero_item=2,
                fornecedor_documento="52998224725",  # CPF válido, mas não cadastrado
                valor_unitario_homologado=Dinheiro.de("1"),
            ),
        ]
    )

    with pytest.raises(ReferenceNotFoundError, match="52998224725"):
        repo.add(contratacao)
    cadastros.commit()

    # tudo ou nada: nem a contratação nem o item 1 ficaram gravados
    assert _count(cadastros, ContratacaoModel) == 0
    assert _count(cadastros, ItemContratacaoModel) == 0


def test_contratacao_add_duplicate_raises_domain_error(cadastros: Session) -> None:
    repo = SqlContratacaoRepository(cadastros)
    repo.add(make_contratacao())

    with pytest.raises(DuplicateEntityError):
        repo.add(make_contratacao())


def test_contratacao_upsert_twice_does_not_duplicate(cadastros: Session) -> None:
    repo = SqlContratacaoRepository(cadastros)
    repo.upsert(_contratacao_com_resultado())
    repo.upsert(_contratacao_com_resultado())
    cadastros.commit()

    assert _count(cadastros, ContratacaoModel) == 1
    assert _count(cadastros, ItemContratacaoModel) == 2


def test_contratacao_upsert_syncs_changes(cadastros: Session) -> None:
    repo = SqlContratacaoRepository(cadastros)
    repo.upsert(_contratacao_com_resultado())

    changed = make_contratacao(
        situacao=SituacaoContratacao.REVOGADA,
        itens=[make_item(numero_item=1, valor_unitario_estimado=Dinheiro.de("10"))],
    )
    repo.upsert(changed)  # item 2 saiu, item 1 mudou de preço
    cadastros.commit()

    assert repo.get(changed.numero_controle_pncp) == changed


def test_contratacao_upsert_without_items_removes_all(cadastros: Session) -> None:
    repo = SqlContratacaoRepository(cadastros)
    repo.upsert(_contratacao_com_resultado())
    repo.upsert(make_contratacao(itens=[]))
    cadastros.commit()

    assert _count(cadastros, ItemContratacaoModel) == 0


def test_database_check_blocks_negative_value(cadastros: Session) -> None:
    """Defesa em profundidade: mesmo pulando o domínio (SQL direto), o banco recusa."""
    SqlContratacaoRepository(cadastros).add(make_contratacao())
    cadastros.commit()

    with pytest.raises(IntegrityError) as exc_info:
        cadastros.execute(text("UPDATE silver.item_contratacao SET valor_unitario_estimado = -1"))

    assert getattr(exc_info.value.orig, "sqlstate", None) == "23514"  # check_violation


def test_deleting_contratacao_cascades_to_items(cadastros: Session) -> None:
    SqlContratacaoRepository(cadastros).add(_contratacao_com_resultado())
    cadastros.commit()

    cadastros.execute(text("DELETE FROM silver.contratacao"))
    cadastros.commit()

    assert _count(cadastros, ItemContratacaoModel) == 0


def test_orgao_with_contratacao_cannot_be_deleted(cadastros: Session) -> None:
    SqlContratacaoRepository(cadastros).add(make_contratacao())
    cadastros.commit()

    with pytest.raises(IntegrityError) as exc_info:
        cadastros.execute(text("DELETE FROM silver.orgao"))

    assert getattr(exc_info.value.orig, "sqlstate", None) == "23503"  # foreign_key_violation


def test_get_after_upsert_in_same_session_is_not_stale(cadastros: Session) -> None:
    """Ler depois de um upsert na mesma sessão devolve o que está no banco.

    O upsert (SQL Core) não atualiza objetos já carregados na sessão. O repositório
    nunca guarda os modelos (o identity map usa referências fracas e os libera), e
    ainda usa `populate_existing` para não depender disso.
    """
    repo = SqlContratacaoRepository(cadastros)
    repo.upsert(make_contratacao(objeto="Objeto original"))
    assert repo.get(f"{CNPJ_ORGAO}-1-000123/2025") is not None  # carrega na sessão

    repo.upsert(make_contratacao(objeto="Objeto corrigido"))
    loaded = repo.get(f"{CNPJ_ORGAO}-1-000123/2025")

    assert loaded is not None
    assert loaded.objeto == "Objeto corrigido"
