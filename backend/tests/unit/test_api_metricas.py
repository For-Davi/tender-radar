"""Testes de /metricas e /categorias (camada gold) com o port trocado por um fake."""

import pytest
from fastapi.testclient import TestClient

from radar.ports.consultas import PaginaPedido
from tests.fakes_consultas import CNPJ_ORGAO, FakeMetricasQueries, make_alerta


def test_categorias(api: TestClient) -> None:
    response = api.get("/categorias")

    assert response.status_code == 200
    assert response.json() == [
        {"material_ou_servico": "M", "ncm_capitulo": None, "nome": "Material sem classificação"},
        {"material_ou_servico": "M", "ncm_capitulo": "30", "nome": "30 - Produtos farmacêuticos"},
    ]


def test_valor_mensal(api: TestClient) -> None:
    body = api.get("/metricas/valor-mensal").json()

    assert body[1] == {
        "mes": "2026-02-01",
        "contratacoes": 0,
        "itens": 0,
        "valor_total_estimado": "0",
        "media_movel_3m": "150.00",
        "meses_na_media": 2,
    }


def test_preco_categoria_with_filter(api: TestClient, fake_metricas: FakeMetricasQueries) -> None:
    body = api.get("/metricas/preco-categoria", params={"categoria": "30"}).json()

    assert fake_metricas.chamadas == [("preco_categoria", "30")]
    assert body == [
        {
            "categoria": {
                "material_ou_servico": "M",
                "ncm_capitulo": "30",
                "nome": "30 - Produtos farmacêuticos",
            },
            "unidade": "UNIDADE",
            "mes": "2026-02-01",
            "itens": 1,
            "preco_medio": "16.5000",
            "preco_mediano": "16.5000",
            "preco_mediano_mes_anterior": "15.0000",
            "variacao_percentual": "10.00",
        }
    ]


def test_preco_categoria_without_filter(
    api: TestClient, fake_metricas: FakeMetricasQueries
) -> None:
    assert api.get("/metricas/preco-categoria").status_code == 200

    assert fake_metricas.chamadas == [("preco_categoria", None)]


def test_ranking_with_masked_cnpj(api: TestClient, fake_metricas: FakeMetricasQueries) -> None:
    body = api.get("/metricas/ranking-fornecedores", params={"orgao": "07.954.480/0001-79"}).json()

    assert fake_metricas.chamadas == [("ranking_fornecedores", CNPJ_ORGAO)]
    assert body[0]["ranking"] == 1
    assert body[0]["participacao_percentual"] == "40.00"


def test_precos_acima_p90_paginated_with_link_to_detail(
    api: TestClient, fake_metricas: FakeMetricasQueries
) -> None:
    fake_metricas.alertas = [make_alerta(n) for n in range(1, 4)]

    body = api.get("/metricas/precos-acima-p90", params={"tamanho_pagina": 2}).json()

    assert fake_metricas.chamadas == [("precos_acima_p90", PaginaPedido(1, 2))]
    assert (body["total"], body["total_paginas"], len(body["itens"])) == (3, 2, 2)
    # o id público permite ao frontend montar o link para GET /contratacoes/{id}
    assert body["itens"][0]["contratacao_id"] == f"{CNPJ_ORGAO}-1-000001-2025"
    assert body["itens"][0]["percentil_preco"] == "1.0000"


def test_precos_acima_p90_page_beyond_last_is_empty(api: TestClient) -> None:
    body = api.get("/metricas/precos-acima-p90", params={"pagina": 5}).json()

    assert body["itens"] == []
    assert body["total"] == 0


@pytest.mark.parametrize(
    ("path", "query", "campo"),
    [
        ("/metricas/preco-categoria", {"categoria": "300"}, "query.categoria"),
        ("/metricas/ranking-fornecedores", {"orgao": "123"}, "query.orgao"),
        ("/metricas/precos-acima-p90", {"tamanho_pagina": "500"}, "query.tamanho_pagina"),
    ],
)
def test_invalid_params_return_422(
    api: TestClient,
    fake_metricas: FakeMetricasQueries,
    path: str,
    query: dict[str, str],
    campo: str,
) -> None:
    response = api.get(path, params=query)

    assert response.status_code == 422
    assert response.json()["erros"][0]["campo"] == campo
    assert fake_metricas.chamadas == []


@pytest.mark.parametrize(
    "path",
    [
        "/categorias",
        "/metricas/valor-mensal",
        "/metricas/preco-categoria",
        "/metricas/ranking-fornecedores",
        "/metricas/precos-acima-p90",
    ],
)
def test_missing_gold_returns_503_problem(
    api: TestClient, fake_metricas: FakeMetricasQueries, path: str
) -> None:
    fake_metricas.indisponivel = True

    response = api.get(path)

    assert response.status_code == 503
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["retry-after"] == "60"
    body = response.json()
    assert body["title"] == "Service Unavailable"
    assert "dbt" in body["detail"]
    # o erro interno (nome de tabela) não vaza para o cliente
    assert "relation" not in body["detail"]
