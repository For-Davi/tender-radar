"""Testes dos mappers domínio <-> modelo e da tradução de erros (sem banco)."""

from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from radar.adapters.postgres.errors import raise_as_domain_error
from radar.adapters.postgres.mappers import (
    contratacao_to_domain,
    contratacao_values,
    fornecedor_to_domain,
    fornecedor_values,
    item_values,
    orgao_to_domain,
    orgao_values,
)
from radar.adapters.postgres.models import (
    ContratacaoModel,
    FornecedorModel,
    ItemContratacaoModel,
    OrgaoModel,
)
from radar.domain.entities import Contratacao
from radar.domain.enums import TipoPessoa
from radar.domain.errors import DuplicateEntityError, ReferenceNotFoundError
from radar.domain.value_objects import Dinheiro
from tests.factories import (
    CNPJ_FORNECEDOR,
    make_contratacao,
    make_fornecedor,
    make_item,
    make_orgao,
)


def test_orgao_roundtrip() -> None:
    orgao = make_orgao()

    assert orgao_to_domain(OrgaoModel(**orgao_values(orgao))) == orgao


@pytest.mark.parametrize(
    ("tipo", "documento"),
    [
        (TipoPessoa.JURIDICA, CNPJ_FORNECEDOR),
        (TipoPessoa.FISICA, "52998224725"),
        (TipoPessoa.ESTRANGEIRA, "AR-30-12345678-9"),
    ],
)
def test_fornecedor_roundtrip(tipo: TipoPessoa, documento: str) -> None:
    fornecedor = make_fornecedor(tipo_pessoa=tipo, documento=documento)

    model = FornecedorModel(**fornecedor_values(fornecedor))

    assert fornecedor_to_domain(model) == fornecedor


def _as_loaded_model(contratacao: Contratacao) -> ContratacaoModel:
    """Simula o que o repositório carrega do banco (com relacionamentos preenchidos)."""
    fornecedores = {
        item.fornecedor_documento: FornecedorModel(documento=item.fornecedor_documento)
        for item in contratacao.itens
        if item.fornecedor_documento
    }
    model = ContratacaoModel(**contratacao_values(contratacao, orgao_id=1))
    model.orgao = OrgaoModel(cnpj=contratacao.orgao_cnpj.value)
    model.itens = [
        ItemContratacaoModel(
            **item_values(item, contratacao_id=1, fornecedor_id=None),
            fornecedor=fornecedores.get(item.fornecedor_documento or ""),
        )
        for item in contratacao.itens
    ]
    return model


def test_contratacao_roundtrip_with_items_and_result() -> None:
    contratacao = make_contratacao(
        valor_total_estimado=Dinheiro.de("12345.6789"),
        itens=[
            make_item(numero_item=1, quantidade=Decimal("2.5")),
            make_item(
                numero_item=2,
                valor_unitario_estimado=Dinheiro.de("0.0345"),
                fornecedor_documento=CNPJ_FORNECEDOR,
                valor_unitario_homologado=Dinheiro.de("0.0301"),
            ),
        ],
    )

    assert contratacao_to_domain(_as_loaded_model(contratacao)) == contratacao


def test_contratacao_roundtrip_without_estimated_value() -> None:
    contratacao = make_contratacao(valor_total_estimado=None, itens=[])

    assert contratacao_to_domain(_as_loaded_model(contratacao)) == contratacao


def test_item_with_unknown_estimate_roundtrip() -> None:
    contratacao = make_contratacao(itens=[make_item(valor_unitario_estimado=None)])

    model = _as_loaded_model(contratacao)

    assert model.itens[0].valor_unitario_estimado is None  # NULL no banco, nunca 0
    assert contratacao_to_domain(model) == contratacao


def test_item_ncm_roundtrip() -> None:
    contratacao = make_contratacao(itens=[make_item(ncm_nbs="90183999")])

    model = _as_loaded_model(contratacao)

    assert model.itens[0].ncm_nbs == "90183999"
    assert contratacao_to_domain(model) == contratacao


def test_contratacao_values_stores_derived_columns() -> None:
    values = contratacao_values(
        make_contratacao(numero_controle_pncp="11222333000181-1-000042/2024"), orgao_id=7
    )

    assert values["ano"] == 2024
    assert values["sequencial"] == 42
    assert values["orgao_id"] == 7
    assert values["modalidade"] == 6  # o código do PNCP, não o nome do enum


def test_values_keep_decimal_exact() -> None:
    values = item_values(
        make_item(valor_unitario_estimado=Dinheiro.de("0.0345")),
        contratacao_id=1,
        fornecedor_id=None,
    )

    assert values["valor_unitario_estimado"] == Decimal("0.0345")
    assert isinstance(values["valor_unitario_estimado"], Decimal)


# ------------------------------------------------------------------ tradução de erros


class _FakeDriverError(Exception):
    """Imita o erro do psycopg, que expõe o código SQLSTATE."""

    def __init__(self, sqlstate: str) -> None:
        super().__init__(f"erro {sqlstate}")
        self.sqlstate = sqlstate


def _integrity_error(sqlstate: str) -> IntegrityError:
    return IntegrityError("INSERT ...", params=None, orig=_FakeDriverError(sqlstate))


def test_unique_violation_becomes_duplicate_entity() -> None:
    with pytest.raises(DuplicateEntityError):
        raise_as_domain_error(_integrity_error("23505"))


def test_foreign_key_violation_becomes_reference_not_found() -> None:
    with pytest.raises(ReferenceNotFoundError):
        raise_as_domain_error(_integrity_error("23503"))


def test_other_integrity_errors_are_not_hidden() -> None:
    # 23514 = CHECK violado: é bug (dado inválido passou pelo domínio), não pode virar erro "normal"
    with pytest.raises(IntegrityError):
        raise_as_domain_error(_integrity_error("23514"))
