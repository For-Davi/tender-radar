"""Schemas do bruto: aplicam a normalização e apontam o campo com problema."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from radar.domain.enums import Modalidade
from radar.pipelines.schemas_bronze import ContratacaoBronze, ItemBronze, ResultadoBronze
from tests.bronze_payloads import fixture_payload


def test_new_pncp_fields_are_ignored() -> None:
    bruto = fixture_payload()["contratacao"] | {"campoQueOPncpCriouAmanha": {"x": 1}}

    contratacao = ContratacaoBronze.model_validate(bruto)

    assert contratacao.modalidade is Modalidade.PREGAO_ELETRONICO


def test_item_applies_cleaning_rules() -> None:
    bruto = fixture_payload()["itens"][0] | {
        "descricao": "  Câmara   conservação ",
        "quantidade": "1.234,5",
        "itemCategoriaNome": "Não se aplica",
    }

    item = ItemBronze.model_validate(bruto)

    assert item.descricao == "Câmara conservação"
    assert item.quantidade == Decimal("1234.5")
    assert item.categoria is None


def test_error_points_to_the_camel_case_field() -> None:
    bruto = fixture_payload()["itens"][0] | {"materialOuServico": "X"}

    with pytest.raises(ValidationError) as info:
        ItemBronze.model_validate(bruto)

    assert info.value.errors()[0]["loc"] == ("materialOuServico",)


def test_result_optional_fields_have_defaults() -> None:
    bruto = {
        "niFornecedor": "12561319000175",
        "tipoPessoa": "PJ",
        "nomeRazaoSocialFornecedor": "Fornecedor",
        "valorUnitarioHomologado": 10,
    }

    resultado = ResultadoBronze.model_validate(bruto)

    assert resultado.data_cancelamento is None
    assert resultado.ordem_classificacao_srp is None
