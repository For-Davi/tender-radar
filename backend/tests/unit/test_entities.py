"""Testes das entidades e regras de negócio do domínio."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from radar.domain.entities import Contratacao, Fornecedor, ItemContratacao, Orgao
from radar.domain.enums import (
    Esfera,
    MaterialOuServico,
    Modalidade,
    Poder,
    SituacaoContratacao,
    TipoPessoa,
)
from radar.domain.errors import BusinessRuleError, InvalidValueError
from radar.domain.value_objects import Cnpj, Dinheiro
from tests.factories import make_contratacao, make_item

# ------------------------------------------------------------------ Enums


def test_modalidade_from_pncp_code() -> None:
    assert Modalidade(6) is Modalidade.PREGAO_ELETRONICO
    assert Modalidade(8) is Modalidade.DISPENSA_DE_LICITACAO


def test_unknown_pncp_code_is_rejected() -> None:
    with pytest.raises(ValueError, match="99"):
        Modalidade(99)


def test_situacao_from_pncp_code() -> None:
    assert SituacaoContratacao(1) is SituacaoContratacao.DIVULGADA


# ------------------------------------------------------------------ Orgao


def test_orgao_valid() -> None:
    orgao = Orgao(
        cnpj=Cnpj("11222333000181"),
        razao_social="Prefeitura Exemplo",
        esfera=Esfera.MUNICIPAL,
        poder=Poder.EXECUTIVO,
    )

    assert orgao.cnpj.value == "11222333000181"


def test_orgao_strips_and_requires_name() -> None:
    with pytest.raises(InvalidValueError, match="razao_social"):
        Orgao(
            cnpj=Cnpj("11222333000181"),
            razao_social="   ",
            esfera=Esfera.FEDERAL,
            poder=Poder.EXECUTIVO,
        )


# ------------------------------------------------------------------ Fornecedor


def test_fornecedor_pj_normalizes_cnpj() -> None:
    fornecedor = Fornecedor(
        tipo_pessoa=TipoPessoa.JURIDICA, documento="11.222.333/0001-81", nome="ACME Ltda"
    )

    assert fornecedor.documento == "11222333000181"


def test_fornecedor_pf_normalizes_cpf() -> None:
    fornecedor = Fornecedor(tipo_pessoa=TipoPessoa.FISICA, documento="529.982.247-25", nome="Ana")

    assert fornecedor.documento == "52998224725"


def test_fornecedor_pj_with_invalid_cnpj_is_rejected() -> None:
    with pytest.raises(InvalidValueError, match="CNPJ"):
        Fornecedor(tipo_pessoa=TipoPessoa.JURIDICA, documento="52998224725", nome="X")


def test_fornecedor_estrangeiro_keeps_raw_document() -> None:
    fornecedor = Fornecedor(
        tipo_pessoa=TipoPessoa.ESTRANGEIRA, documento=" AR-30-12345678-9 ", nome="Foreign SA"
    )

    assert fornecedor.documento == "AR-30-12345678-9"


def test_fornecedor_estrangeiro_requires_document() -> None:
    with pytest.raises(InvalidValueError, match="documento"):
        Fornecedor(tipo_pessoa=TipoPessoa.ESTRANGEIRA, documento="  ", nome="Foreign SA")


# ------------------------------------------------------------------ ItemContratacao


def test_item_total_is_quantity_times_unit_price() -> None:
    item = make_item(quantidade=Decimal("3"), valor_unitario_estimado=Dinheiro.de("2.50"))

    assert item.valor_total_estimado == Dinheiro.de("7.50")


def test_item_with_unknown_estimate_has_unknown_total() -> None:
    # orçamento sigiloso: o PNCP manda 0, mas o valor é desconhecido, não zero
    item = make_item(valor_unitario_estimado=None)

    assert item.valor_unitario_estimado is None
    assert item.valor_total_estimado is None


def test_contratacao_total_of_items_is_unknown_if_any_item_is_unknown() -> None:
    contratacao = make_contratacao(
        itens=[make_item(numero_item=1), make_item(numero_item=2, valor_unitario_estimado=None)]
    )

    # somar o desconhecido como 0 daria um total falsamente baixo
    assert contratacao.valor_total_itens() is None


@pytest.mark.parametrize("quantidade", [Decimal("0"), Decimal("-1")])
def test_item_quantity_must_be_positive(quantidade: Decimal) -> None:
    with pytest.raises(BusinessRuleError, match="quantidade"):
        make_item(quantidade=quantidade)


def test_item_quantity_rejects_float() -> None:
    with pytest.raises(InvalidValueError, match="float"):
        make_item(quantidade=1.5)


def test_item_negative_unit_price_is_rejected() -> None:
    with pytest.raises(BusinessRuleError, match="negativo"):
        make_item(valor_unitario_estimado=Dinheiro.de("-0.01"))


def test_item_negative_homologated_price_is_rejected() -> None:
    with pytest.raises(BusinessRuleError, match="negativo"):
        make_item(
            fornecedor_documento="11222333000181", valor_unitario_homologado=Dinheiro.de("-1")
        )


def test_item_numero_must_be_positive() -> None:
    with pytest.raises(BusinessRuleError, match="numero_item"):
        make_item(numero_item=0)


def test_item_requires_description() -> None:
    with pytest.raises(InvalidValueError, match="descricao"):
        make_item(descricao="")


@pytest.mark.parametrize(
    ("fornecedor", "homologado"),
    [("11222333000181", None), (None, Dinheiro.de("10"))],
)
def test_item_result_requires_both_supplier_and_price(
    fornecedor: str | None, homologado: Dinheiro | None
) -> None:
    with pytest.raises(BusinessRuleError, match="juntos"):
        make_item(fornecedor_documento=fornecedor, valor_unitario_homologado=homologado)


def test_item_with_result() -> None:
    item = make_item(
        fornecedor_documento="11222333000181", valor_unitario_homologado=Dinheiro.de("9")
    )

    assert item.tem_resultado


# ------------------------------------------------------------------ Contratacao


def test_contratacao_derives_ano_and_sequencial_from_numero_controle() -> None:
    contratacao = make_contratacao(numero_controle_pncp="11222333000181-1-000123/2025")

    assert contratacao.ano == 2025
    assert contratacao.sequencial == 123


def test_contratacao_accepts_alphanumeric_cnpj_in_numero_controle() -> None:
    contratacao = make_contratacao(numero_controle_pncp="12ABC34501DE35-1-000001/2026")

    assert contratacao.ano == 2026


@pytest.mark.parametrize(
    "numero",
    [
        "11222333000181-1-123/2025",  # sequencial sem os 6 dígitos
        "11222333000181-2-000123/2025",  # tipo diferente de 1 (contratação)
        "11222333000181-1-000123/25",  # ano com 2 dígitos
        "1122233300018-1-000123/2025",  # CNPJ curto
        "",
    ],
)
def test_contratacao_invalid_numero_controle_is_rejected(numero: str) -> None:
    with pytest.raises(InvalidValueError, match="numero_controle_pncp"):
        make_contratacao(numero_controle_pncp=numero)


def test_contratacao_rejects_negative_estimated_value() -> None:
    with pytest.raises(BusinessRuleError, match="negativo"):
        make_contratacao(valor_total_estimado=Dinheiro.de("-1"))


def test_contratacao_accepts_missing_estimated_value() -> None:
    # o PNCP permite valor sigiloso: o campo vem nulo
    assert make_contratacao(valor_total_estimado=None).valor_total_estimado is None


def test_contratacao_requires_timezone_aware_date() -> None:
    with pytest.raises(InvalidValueError, match="fuso"):
        make_contratacao(data_publicacao=datetime(2025, 3, 10, 9, 0))


@pytest.mark.parametrize("uf", ["XX", "ce", "C", ""])
def test_contratacao_invalid_uf_is_rejected(uf: str) -> None:
    with pytest.raises(InvalidValueError, match="UF"):
        make_contratacao(uf=uf)


def test_contratacao_rejects_duplicated_item_numbers_in_constructor() -> None:
    with pytest.raises(BusinessRuleError, match="duplicado"):
        make_contratacao(itens=[make_item(numero_item=1), make_item(numero_item=1)])


def test_contratacao_add_item_rejects_duplicate() -> None:
    contratacao = make_contratacao(itens=[make_item(numero_item=1)])

    with pytest.raises(BusinessRuleError, match="duplicado"):
        contratacao.add_item(make_item(numero_item=1))

    assert len(contratacao.itens) == 1  # o item inválido não entrou


def test_contratacao_add_item_and_total() -> None:
    contratacao = make_contratacao(itens=[])
    contratacao.add_item(
        make_item(
            numero_item=1, quantidade=Decimal("1"), valor_unitario_estimado=Dinheiro.de("0.1")
        )
    )
    contratacao.add_item(
        make_item(
            numero_item=2, quantidade=Decimal("2"), valor_unitario_estimado=Dinheiro.de("0.2")
        )
    )

    assert contratacao.valor_total_itens() == Dinheiro.de("0.5")


def test_contratacao_itens_are_read_only_view() -> None:
    contratacao = make_contratacao(itens=[make_item()])

    assert isinstance(contratacao.itens, tuple)  # só muda via add_item (que valida)


def test_contratacao_with_all_fields() -> None:
    contratacao = Contratacao(
        numero_controle_pncp="11222333000181-1-000001/2025",
        orgao_cnpj=Cnpj("11222333000181"),
        modalidade=Modalidade.PREGAO_ELETRONICO,
        situacao=SituacaoContratacao.DIVULGADA,
        objeto="Aquisição de computadores",
        valor_total_estimado=Dinheiro.de("100000"),
        data_publicacao=datetime(2025, 3, 10, 9, 0, tzinfo=UTC),
        uf="CE",
        municipio="Fortaleza",
        itens=[
            ItemContratacao(
                numero_item=1,
                descricao="Notebook",
                material_ou_servico=MaterialOuServico.MATERIAL,
                categoria="Informática",
                quantidade=Decimal("10"),
                unidade_medida="UN",
                valor_unitario_estimado=Dinheiro.de("5000"),
            )
        ],
    )

    assert contratacao.valor_total_itens() == Dinheiro.de("50000")


def test_item_ncm_is_optional_and_validated() -> None:
    assert make_item().ncm_nbs is None
    assert make_item(ncm_nbs="90183999").ncm_nbs == "90183999"
    with pytest.raises(InvalidValueError, match="NCM"):
        make_item(ncm_nbs="90.18")
