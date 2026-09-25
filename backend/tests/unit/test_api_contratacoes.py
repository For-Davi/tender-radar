"""Testes de /contratacoes com o port trocado por um fake (sem banco).

Provam a camada HTTP: query string -> filtro, validação (422), envelope de
paginação, formato do JSON e 404. A filtragem em SQL é provada na integração.
"""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from radar.ports.consultas import (
    ContratacaoDetalhe,
    FiltroContratacoes,
    Ordenacao,
    PaginaPedido,
)
from tests.fakes_consultas import (
    CNPJ_ORGAO,
    VENCEDOR,
    FakeContratacaoQueries,
    make_item_detalhe,
    make_resumo,
)

ID_1 = f"{CNPJ_ORGAO}-1-000001-2025"


def _seed(fake: FakeContratacaoQueries, quantidade: int) -> None:
    fake.contratacoes = [
        ContratacaoDetalhe(make_resumo(n), [make_item_detalhe()]) for n in range(1, quantidade + 1)
    ]


# ------------------------------------------------------------------ lista: sucesso


def test_list_returns_envelope_and_items(
    api: TestClient, fake_contratacoes: FakeContratacaoQueries
) -> None:
    _seed(fake_contratacoes, 2)

    response = api.get("/contratacoes")

    assert response.status_code == 200
    body = response.json()
    assert body | {"itens": None} == {
        "itens": None,
        "total": 2,
        "pagina": 1,
        "tamanho_pagina": 20,
        "total_paginas": 1,
    }
    assert body["itens"][0] == {
        "id": ID_1,
        "numero_controle_pncp": f"{CNPJ_ORGAO}-1-000001/2025",
        "orgao": {"cnpj": CNPJ_ORGAO, "razao_social": "Estado do Ceará"},
        "modalidade": 6,
        "modalidade_nome": "Pregão eletrônico",
        "situacao": 1,
        "situacao_nome": "Divulgada no PNCP",
        "objeto": "Objeto 1",
        "valor_total_estimado": "1500.5000",  # dinheiro como texto: nunca float
        "data_publicacao": "2025-03-10T15:00:00Z",
        "uf": "CE",
        "municipio": "Fortaleza",
        "total_itens": 2,
    }


def test_list_without_params_uses_defaults(
    api: TestClient, fake_contratacoes: FakeContratacaoQueries
) -> None:
    api.get("/contratacoes")

    assert fake_contratacoes.chamadas == [
        (FiltroContratacoes(), Ordenacao.DATA_DESC, PaginaPedido(1, 20))
    ]


def test_secret_value_is_null(api: TestClient, fake_contratacoes: FakeContratacaoQueries) -> None:
    fake_contratacoes.contratacoes = [
        ContratacaoDetalhe(make_resumo(1, valor_total_estimado=None), [])
    ]

    item = api.get("/contratacoes").json()["itens"][0]

    assert item["valor_total_estimado"] is None


# ------------------------------------------------------------------ lista: filtros


@pytest.mark.parametrize(
    ("query", "esperado"),
    [
        ({"uf": "CE"}, FiltroContratacoes(uf="CE")),
        ({"uf": "ce"}, FiltroContratacoes(uf="CE")),  # normaliza para maiúsculas
        ({"orgao": CNPJ_ORGAO}, FiltroContratacoes(orgao_cnpj=CNPJ_ORGAO)),
        # com máscara: chega ao port sem máscara
        ({"orgao": "07.954.480/0001-79"}, FiltroContratacoes(orgao_cnpj=CNPJ_ORGAO)),
        ({"categoria": "30"}, FiltroContratacoes(categoria="30")),
        ({"data_inicio": "2025-03-01"}, FiltroContratacoes(data_inicio=date(2025, 3, 1))),
        ({"data_fim": "2025-03-31"}, FiltroContratacoes(data_fim=date(2025, 3, 31))),
        ({"valor_min": "1000.50"}, FiltroContratacoes(valor_min=Decimal("1000.50"))),
        ({"valor_max": "0"}, FiltroContratacoes(valor_max=Decimal(0))),
    ],
)
def test_each_filter_reaches_the_port(
    api: TestClient,
    fake_contratacoes: FakeContratacaoQueries,
    query: dict[str, str],
    esperado: FiltroContratacoes,
) -> None:
    assert api.get("/contratacoes", params=query).status_code == 200

    filtro, _, _ = fake_contratacoes.chamadas[0]
    assert filtro == esperado


def test_combined_filters_reach_the_port_together(
    api: TestClient, fake_contratacoes: FakeContratacaoQueries
) -> None:
    query = {
        "uf": "CE",
        "orgao": CNPJ_ORGAO,
        "categoria": "30",
        "data_inicio": "2025-03-01",
        "data_fim": "2025-03-01",  # mesmo dia: intervalo válido
        "valor_min": "100",
        "valor_max": "100",
        "ordenar": "-valor_total_estimado",
        "pagina": "2",
        "tamanho_pagina": "5",
    }

    assert api.get("/contratacoes", params=query).status_code == 200

    assert fake_contratacoes.chamadas == [
        (
            FiltroContratacoes(
                uf="CE",
                orgao_cnpj=CNPJ_ORGAO,
                categoria="30",
                data_inicio=date(2025, 3, 1),
                data_fim=date(2025, 3, 1),
                valor_min=Decimal(100),
                valor_max=Decimal(100),
            ),
            Ordenacao.VALOR_DESC,
            PaginaPedido(2, 5),
        )
    ]


@pytest.mark.parametrize("ordenar", [o.value for o in Ordenacao])
def test_every_ordering_is_accepted(
    api: TestClient, fake_contratacoes: FakeContratacaoQueries, ordenar: str
) -> None:
    assert api.get("/contratacoes", params={"ordenar": ordenar}).status_code == 200

    assert fake_contratacoes.chamadas[0][1] == Ordenacao(ordenar)


# ------------------------------------------------------------------ lista: paginação


@pytest.mark.parametrize(
    ("pagina", "itens_na_pagina", "primeiro_objeto"),
    [
        (1, 10, "Objeto 1"),  # primeira
        (3, 5, "Objeto 21"),  # última (incompleta)
        (4, 0, None),  # além da última: vazia, mas 200
    ],
)
def test_pagination(
    api: TestClient,
    fake_contratacoes: FakeContratacaoQueries,
    pagina: int,
    itens_na_pagina: int,
    primeiro_objeto: str | None,
) -> None:
    _seed(fake_contratacoes, 25)

    response = api.get("/contratacoes", params={"pagina": pagina, "tamanho_pagina": 10})

    assert response.status_code == 200
    body = response.json()
    assert (body["total"], body["total_paginas"], body["pagina"]) == (25, 3, pagina)
    assert len(body["itens"]) == itens_na_pagina
    if primeiro_objeto:
        assert body["itens"][0]["objeto"] == primeiro_objeto


def test_empty_result(api: TestClient) -> None:
    body = api.get("/contratacoes").json()

    assert body == {"itens": [], "total": 0, "pagina": 1, "tamanho_pagina": 20, "total_paginas": 0}


# ------------------------------------------------------------------ lista: 422


@pytest.mark.parametrize(
    ("query", "campo"),
    [
        ({"uf": "XX"}, "query.uf"),
        ({"orgao": "11111111111111"}, "query.orgao"),  # dígitos verificadores errados
        ({"categoria": "3"}, "query.categoria"),
        ({"categoria": "ab"}, "query.categoria"),
        ({"data_inicio": "2025-13-01"}, "query.data_inicio"),
        ({"valor_min": "-1"}, "query.valor_min"),
        ({"valor_max": "abc"}, "query.valor_max"),
        ({"ordenar": "objeto"}, "query.ordenar"),
        ({"pagina": "0"}, "query.pagina"),
        ({"tamanho_pagina": "0"}, "query.tamanho_pagina"),
        ({"tamanho_pagina": "101"}, "query.tamanho_pagina"),
    ],
)
def test_invalid_param_returns_422_naming_the_field(
    api: TestClient, fake_contratacoes: FakeContratacaoQueries, query: dict[str, str], campo: str
) -> None:
    response = api.get("/contratacoes", params=query)

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert [erro["campo"] for erro in response.json()["erros"]] == [campo]
    assert fake_contratacoes.chamadas == []  # nem chegou a consultar


@pytest.mark.parametrize(
    ("query", "mensagem"),
    [
        ({"data_inicio": "2025-03-02", "data_fim": "2025-03-01"}, "data_inicio"),
        ({"valor_min": "200", "valor_max": "100"}, "valor_min"),
    ],
)
def test_inverted_ranges_return_422(api: TestClient, query: dict[str, str], mensagem: str) -> None:
    response = api.get("/contratacoes", params=query)

    assert response.status_code == 422
    assert mensagem in response.json()["erros"][0]["mensagem"]


# ------------------------------------------------------------------ detalhe


def _detalhe_com_itens() -> ContratacaoDetalhe:
    return ContratacaoDetalhe(
        make_resumo(1),
        [
            make_item_detalhe(1),
            make_item_detalhe(
                2,
                vencedor=VENCEDOR,
                valor_unitario_homologado=Decimal("0.3000"),
            ),
            make_item_detalhe(3, valor_unitario_estimado=None, ncm_nbs=None),
        ],
    )


def test_detail_returns_contratacao_with_items(
    api: TestClient, fake_contratacoes: FakeContratacaoQueries
) -> None:
    fake_contratacoes.contratacoes = [_detalhe_com_itens()]

    response = api.get(f"/contratacoes/{ID_1}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == ID_1
    assert body["orgao"]["razao_social"] == "Estado do Ceará"
    itens: list[dict[str, Any]] = body["itens"]
    assert [item["numero_item"] for item in itens] == [1, 2, 3]
    assert itens[0] | {"numero_item": None} == {
        "numero_item": None,
        "descricao": "Dipirona 500mg",
        "material_ou_servico": "M",
        "material_ou_servico_nome": "Material",
        "ncm_nbs": "30049099",
        "quantidade": "10.0000",
        "unidade_medida": "Unidade",
        "valor_unitario_estimado": "0.3333",
        "valor_total_estimado": "3.3330",  # calculado, com 4 casas
        "vencedor": None,
        "valor_unitario_homologado": None,
    }


def test_detail_item_with_winner(
    api: TestClient, fake_contratacoes: FakeContratacaoQueries
) -> None:
    fake_contratacoes.contratacoes = [_detalhe_com_itens()]

    item = api.get(f"/contratacoes/{ID_1}").json()["itens"][1]

    assert item["vencedor"] == {
        "documento": "12ABC34501DE35",
        "nome": "Farmácia Exemplo Ltda",
        "tipo_pessoa": "PJ",
        "tipo_pessoa_nome": "Pessoa jurídica",
    }
    assert item["valor_unitario_homologado"] == "0.3000"


def test_detail_secret_item_has_null_totals(
    api: TestClient, fake_contratacoes: FakeContratacaoQueries
) -> None:
    fake_contratacoes.contratacoes = [_detalhe_com_itens()]

    item = api.get(f"/contratacoes/{ID_1}").json()["itens"][2]

    assert item["valor_unitario_estimado"] is None
    assert item["valor_total_estimado"] is None


def test_detail_not_found_returns_404_problem(api: TestClient) -> None:
    response = api.get(f"/contratacoes/{ID_1}")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json() == {
        "type": "about:blank",
        "title": "Not Found",
        "status": 404,
        "detail": f"contratação não encontrada: {ID_1}",
        "instance": f"/contratacoes/{ID_1}",
    }


@pytest.mark.parametrize(
    "id_invalido",
    [
        "123",
        f"{CNPJ_ORGAO}-1-000001-25",
        f"{CNPJ_ORGAO}-2-000001-2025",
    ],
)
def test_detail_malformed_id_returns_422(api: TestClient, id_invalido: str) -> None:
    response = api.get(f"/contratacoes/{id_invalido}")

    assert response.status_code == 422
    assert response.json()["erros"][0]["campo"] == "path.id"


def test_detail_with_encoded_slash_matches_no_route(api: TestClient) -> None:
    # o %2F é decodificado para "/" antes do roteamento: o caminho vira dois segmentos
    # e nenhuma rota casa (404). É o motivo de o id público não ter barra.
    response = api.get(f"/contratacoes/{CNPJ_ORGAO}-1-000001%2F2025")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
