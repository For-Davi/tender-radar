"""Transformação de uma versão da bronze em entidades da silver (+ rejeições)."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from radar.domain.enums import Esfera, Modalidade, Poder, SituacaoContratacao, TipoPessoa
from radar.domain.value_objects import Cnpj, Dinheiro
from radar.pipelines.transformacao import Transformacao, transformar
from radar.ports.silver import MotivoRejeicao, Rejeicao
from tests.bronze_payloads import (
    CNPJ_FORNECEDOR_FIXTURE,
    CNPJ_ORGAO_FIXTURE,
    NUMERO_FIXTURE,
    fixture_payload,
    make_version,
)


def _run(payload: dict[str, Any]) -> Transformacao:
    return transformar(make_version(payload))


def _only_rejection(result: Transformacao) -> Rejeicao:
    (rejeicao,) = result.rejeicoes
    return rejeicao


def _resultado(**overrides: Any) -> dict[str, Any]:
    resultado: dict[str, Any] = fixture_payload()["resultados"]["1"][0]
    return resultado | overrides


# ------------------------------------------------------------------ caminho feliz (dado real)


def test_real_payload_becomes_clean_entities() -> None:
    result = _run(fixture_payload())

    assert result.rejeicoes == ()
    assert result.limpa is not None
    contratacao = result.limpa.contratacao
    assert contratacao.numero_controle_pncp == NUMERO_FIXTURE
    assert contratacao.orgao_cnpj == Cnpj(CNPJ_ORGAO_FIXTURE)
    assert contratacao.modalidade is Modalidade.PREGAO_ELETRONICO
    assert contratacao.situacao is SituacaoContratacao.DIVULGADA
    assert contratacao.uf == "CE"
    assert contratacao.municipio == "Fortaleza"
    # float JSON 5367337.33 -> Decimal exato, sem resíduo binário
    assert contratacao.valor_total_estimado == Dinheiro.de("5367337.33")
    # "2025-03-10T07:15:44" sem fuso = Brasília = 10:15:44 UTC
    assert contratacao.data_publicacao == datetime(2025, 3, 10, 10, 15, 44, tzinfo=UTC)
    assert [i.numero_item for i in contratacao.itens] == [1, 2, 3]


def test_real_item_values_and_result() -> None:
    result = _run(fixture_payload())
    assert result.limpa is not None

    item = result.limpa.contratacao.itens[0]
    assert item.valor_unitario_estimado == Dinheiro.de("29095.0775")
    assert item.quantidade == Decimal("114")
    assert item.categoria is None  # "Não se aplica" não é categoria
    # o resultado da fixture (1º colocado) vira fornecedor + preço homologado
    assert item.fornecedor_documento == CNPJ_FORNECEDOR_FIXTURE
    assert item.valor_unitario_homologado == Dinheiro.de("11500")


def test_real_orgao_and_fornecedor() -> None:
    result = _run(fixture_payload())
    assert result.limpa is not None

    orgao = result.limpa.orgao
    assert orgao.cnpj == Cnpj(CNPJ_ORGAO_FIXTURE)
    assert orgao.esfera is Esfera.ESTADUAL
    assert orgao.poder is Poder.NAO_SE_APLICA
    (fornecedor,) = result.limpa.fornecedores
    assert fornecedor.documento == CNPJ_FORNECEDOR_FIXTURE
    assert fornecedor.tipo_pessoa is TipoPessoa.JURIDICA


def test_item_flagged_with_result_but_without_results_has_no_result() -> None:
    # itens 2 e 3 têm temResultado=true, mas a fixture só tem resultado do item 1
    result = _run(fixture_payload())
    assert result.limpa is not None

    assert not result.limpa.contratacao.itens[1].tem_resultado
    assert result.rejeicoes == ()


def test_orgao_without_esfera_is_accepted() -> None:
    # dado real (consórcio público de saúde de Iguatu-CE): esferaId "N" = não se aplica
    payload = fixture_payload()
    payload["contratacao"]["orgaoEntidade"]["esferaId"] = "N"

    result = _run(payload)

    assert result.limpa is not None
    assert result.limpa.orgao.esfera is Esfera.NAO_SE_APLICA


def test_masked_cnpj_is_normalized() -> None:
    payload = fixture_payload()
    payload["contratacao"]["orgaoEntidade"]["cnpj"] = "07.954.480/0001-79"

    result = _run(payload)

    assert result.limpa is not None
    assert result.limpa.orgao.cnpj.value == CNPJ_ORGAO_FIXTURE


def test_consistent_total_is_not_flagged() -> None:
    result = _run(fixture_payload())

    assert result.limpa is not None
    assert not result.limpa.inconsistente


def test_total_diverging_from_items_is_flagged_but_saved() -> None:
    payload = fixture_payload()
    payload["contratacao"]["valorTotalEstimado"] = 1000.0  # itens somam ~5,3 milhões

    result = _run(payload)

    assert result.limpa is not None  # a divergência existe na fonte: sinaliza, não rejeita
    assert result.limpa.inconsistente


# ------------------------------------------------------------------ orçamento sigiloso


def test_sigiloso_item_has_unknown_estimate_not_zero() -> None:
    payload = fixture_payload()
    payload["itens"][0] |= {"orcamentoSigiloso": True, "valorUnitarioEstimado": 0}

    result = _run(payload)

    assert result.limpa is not None
    assert result.limpa.contratacao.itens[0].valor_unitario_estimado is None


def test_zero_total_with_all_items_sigilosos_becomes_unknown() -> None:
    payload = fixture_payload()
    payload["contratacao"]["valorTotalEstimado"] = 0
    for item in payload["itens"]:
        item |= {"orcamentoSigiloso": True, "valorUnitarioEstimado": 0}

    result = _run(payload)

    assert result.limpa is not None
    assert result.limpa.contratacao.valor_total_estimado is None
    assert not result.limpa.inconsistente  # desconhecido não é divergente


# ------------------------------------------------------------------ rejeição da contratação


def test_missing_required_field_rejects_contratacao_with_field_path() -> None:
    payload = fixture_payload()
    del payload["contratacao"]["orgaoEntidade"]["cnpj"]

    result = _run(payload)

    assert result.limpa is None
    rejeicao = _only_rejection(result)
    assert rejeicao.motivo is MotivoRejeicao.CAMPO_INVALIDO
    assert rejeicao.numero_item is None
    assert rejeicao.numero_controle_pncp == NUMERO_FIXTURE
    assert [p.campo for p in rejeicao.problemas] == ["contratacao.orgaoEntidade.cnpj"]


def test_invalid_date_rejects_contratacao() -> None:
    payload = fixture_payload()
    payload["contratacao"]["dataPublicacaoPncp"] = "2025-02-30T10:00:00"

    rejeicao = _only_rejection(_run(payload))

    assert rejeicao.motivo is MotivoRejeicao.CAMPO_INVALIDO
    assert rejeicao.problemas[0].campo == "contratacao.dataPublicacaoPncp"
    assert "data inválida" in rejeicao.problemas[0].erro


def test_unknown_modalidade_code_rejects_contratacao() -> None:
    payload = fixture_payload()
    payload["contratacao"]["modalidadeId"] = 99

    rejeicao = _only_rejection(_run(payload))

    assert rejeicao.motivo is MotivoRejeicao.CAMPO_INVALIDO
    assert rejeicao.problemas[0].campo == "contratacao.modalidadeId"


def test_invalid_uf_rejects_whole_contratacao() -> None:
    payload = fixture_payload()
    payload["contratacao"]["unidadeOrgao"]["ufSigla"] = "XX"

    result = _run(payload)

    assert result.limpa is None
    rejeicao = _only_rejection(result)
    assert rejeicao.motivo is MotivoRejeicao.CAMPO_INVALIDO
    assert "UF" in rejeicao.problemas[0].erro


def test_invalid_cnpj_check_digit_rejects_contratacao() -> None:
    payload = fixture_payload()
    payload["contratacao"]["orgaoEntidade"]["cnpj"] = "07954480000178"

    rejeicao = _only_rejection(_run(payload))

    assert rejeicao.motivo is MotivoRejeicao.CAMPO_INVALIDO
    assert "CNPJ" in rejeicao.problemas[0].erro


def test_negative_total_is_a_business_rule_violation() -> None:
    payload = fixture_payload()
    payload["contratacao"]["valorTotalEstimado"] = -1

    rejeicao = _only_rejection(_run(payload))

    assert rejeicao.motivo is MotivoRejeicao.REGRA_NEGOCIO


def test_payload_without_contratacao_is_rejected() -> None:
    rejeicao = _only_rejection(_run({"itens": []}))

    assert rejeicao.motivo is MotivoRejeicao.CAMPO_INVALIDO
    assert rejeicao.problemas[0].campo == "contratacao"


# ------------------------------------------------------------------ rejeição de item


def test_item_with_zero_quantity_is_rejected_alone() -> None:
    payload = fixture_payload()
    payload["itens"][1]["quantidade"] = 0

    result = _run(payload)

    assert result.limpa is not None  # a contratação e os outros itens seguem
    assert [i.numero_item for i in result.limpa.contratacao.itens] == [1, 3]
    rejeicao = _only_rejection(result)
    assert rejeicao.motivo is MotivoRejeicao.REGRA_NEGOCIO
    assert rejeicao.numero_item == 2


def test_item_with_bad_number_format_is_rejected_with_path() -> None:
    payload = fixture_payload()
    payload["itens"][2]["quantidade"] = "muitos"

    rejeicao = _only_rejection(_run(payload))

    assert rejeicao.motivo is MotivoRejeicao.CAMPO_INVALIDO
    assert rejeicao.numero_item == 3
    assert rejeicao.problemas[0].campo == "itens[2].quantidade"


def test_brazilian_formatted_quantity_is_accepted() -> None:
    payload = fixture_payload()
    payload["itens"][0]["quantidade"] = "1.234,5"

    result = _run(payload)

    assert result.limpa is not None
    assert result.limpa.contratacao.itens[0].quantidade == Decimal("1234.5")


def test_duplicated_item_keeps_first_and_rejects_second() -> None:
    payload = fixture_payload()
    payload["itens"][2]["numeroItem"] = 1

    result = _run(payload)

    assert result.limpa is not None
    assert [i.numero_item for i in result.limpa.contratacao.itens] == [1, 2]
    rejeicao = _only_rejection(result)
    assert rejeicao.motivo is MotivoRejeicao.ITEM_DUPLICADO
    assert rejeicao.numero_item == 1


def test_all_items_rejected_keeps_contratacao_without_items() -> None:
    payload = fixture_payload()
    for item in payload["itens"]:
        item["descricao"] = "   "

    result = _run(payload)

    assert result.limpa is not None
    assert result.limpa.contratacao.itens == ()
    assert len(result.rejeicoes) == 3


# ------------------------------------------------------------------ resultados


def test_cancelled_result_is_ignored() -> None:
    payload = fixture_payload()
    payload["resultados"]["1"] = [_resultado(dataCancelamento="2025-04-10T10:00:00")]

    result = _run(payload)

    assert result.limpa is not None
    assert not result.limpa.contratacao.itens[0].tem_resultado
    assert result.limpa.fornecedores == ()


def test_srp_first_place_wins() -> None:
    payload = fixture_payload()
    payload["resultados"]["1"] = [
        _resultado(ordemClassificacaoSrp=2, valorUnitarioHomologado=12000.0, sequencialResultado=1),
        _resultado(ordemClassificacaoSrp=1, valorUnitarioHomologado=11500.0, sequencialResultado=2),
    ]

    result = _run(payload)

    assert result.limpa is not None
    assert result.limpa.contratacao.itens[0].valor_unitario_homologado == Dinheiro.de("11500")


def test_without_srp_order_the_first_result_wins() -> None:
    payload = fixture_payload()
    payload["resultados"]["1"] = [
        _resultado(ordemClassificacaoSrp=None, sequencialResultado=2, valorUnitarioHomologado=2.0),
        _resultado(ordemClassificacaoSrp=None, sequencialResultado=1, valorUnitarioHomologado=1.0),
    ]

    result = _run(payload)

    assert result.limpa is not None
    assert result.limpa.contratacao.itens[0].valor_unitario_homologado == Dinheiro.de("1")


def test_result_with_invalid_supplier_document_rejects_item() -> None:
    payload = fixture_payload()
    payload["resultados"]["1"] = [_resultado(niFornecedor="12561319000100")]

    result = _run(payload)

    assert result.limpa is not None
    assert [i.numero_item for i in result.limpa.contratacao.itens] == [2, 3]
    rejeicao = _only_rejection(result)
    assert rejeicao.motivo is MotivoRejeicao.RESULTADO_INVALIDO
    assert rejeicao.numero_item == 1
    assert rejeicao.problemas[0].campo == "resultados.1[0]"


def test_result_with_missing_price_rejects_item_with_path() -> None:
    payload = fixture_payload()
    resultado = _resultado()
    del resultado["valorUnitarioHomologado"]
    payload["resultados"]["1"] = [resultado]

    rejeicao = _only_rejection(_run(payload))

    assert rejeicao.motivo is MotivoRejeicao.RESULTADO_INVALIDO
    assert rejeicao.problemas[0].campo == "resultados.1[0].valorUnitarioHomologado"


@pytest.mark.parametrize(("tipo", "documento"), [("PF", "52998224725"), ("PE", "AR-30-1234")])
def test_supplier_person_types(tipo: str, documento: str) -> None:
    payload = fixture_payload()
    payload["resultados"]["1"] = [_resultado(tipoPessoa=tipo, niFornecedor=documento)]

    result = _run(payload)

    assert result.limpa is not None
    (fornecedor,) = result.limpa.fornecedores
    assert fornecedor.tipo_pessoa == TipoPessoa(tipo)


def test_same_supplier_in_many_items_appears_once() -> None:
    payload = fixture_payload()
    payload["resultados"]["2"] = [_resultado(numeroItem=2)]

    result = _run(payload)

    assert result.limpa is not None
    assert len(result.limpa.fornecedores) == 1
