"""/metricas e /categorias contra um Postgres real, com a gold criada a partir de `gold.py`.

As linhas da gold são escritas à mão (como nos unit tests do dbt): aqui o que se
testa são os joins com as dimensões, os filtros, a ordenação e a paginação da API.
O cálculo dos marts é testado no dbt (Etapa 04).
"""

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, Table, insert

from radar.adapters.postgres.gold import (
    dim_categoria,
    dim_fornecedor,
    dim_orgao,
    mart_percentil_preco_item,
    mart_preco_categoria_mensal,
    mart_ranking_fornecedor_orgao,
    mart_valor_contratado_mensal,
)

CNPJ_A, CNPJ_B = "11222333000181", "07954480000179"


def _insert(engine: Engine, table: Table, rows: list[dict[str, object]]) -> None:
    with engine.begin() as conn:
        conn.execute(insert(table), rows)


@pytest.fixture
def gold_com_dados(gold: Engine) -> Engine:
    _insert(
        gold,
        dim_categoria,
        [
            {"categoria_key": "k30", "material_ou_servico": "M", "ncm_capitulo": "30",
             "categoria_nome": "30 - Produtos farmacêuticos"},
            {"categoria_key": "kM", "material_ou_servico": "M", "ncm_capitulo": None,
             "categoria_nome": "Material sem classificação"},
            {"categoria_key": "kS", "material_ou_servico": "S", "ncm_capitulo": None,
             "categoria_nome": "Serviço sem classificação"},
        ],
    )  # fmt: skip
    _insert(
        gold,
        dim_orgao,
        [
            {"orgao_key": "oA", "cnpj": CNPJ_A, "razao_social": "Prefeitura A"},
            {"orgao_key": "oB", "cnpj": CNPJ_B, "razao_social": "Estado B"},
        ],
    )
    _insert(
        gold,
        dim_fornecedor,
        [
            {"fornecedor_key": "f1", "documento": "12ABC34501DE35", "nome": "Fornecedor 1"},
            {"fornecedor_key": "f2", "documento": "11444777000161", "nome": "Fornecedor 2"},
        ],
    )
    _insert(
        gold,
        mart_valor_contratado_mensal,
        [
            {"mes": date(2026, 2, 1), "contratacoes": 0, "itens": 0,
             "valor_total_estimado": 0, "media_movel_3m": Decimal("150.00"), "meses_na_media": 2},
            {"mes": date(2026, 1, 1), "contratacoes": 1, "itens": 2,
             "valor_total_estimado": 300, "media_movel_3m": Decimal("300.00"), "meses_na_media": 1},
        ],
    )  # fmt: skip
    _insert(
        gold,
        mart_preco_categoria_mensal,
        [
            {"categoria_key": "k30", "unidade_normalizada": "UNIDADE", "mes": date(2026, 2, 1),
             "itens": 1, "preco_medio": 16.5, "preco_mediano": 16.5,
             "preco_mediano_mes_anterior": 15, "variacao_percentual": Decimal("10.00")},
            {"categoria_key": "k30", "unidade_normalizada": "UNIDADE", "mes": date(2026, 1, 1),
             "itens": 2, "preco_medio": 15, "preco_mediano": 15,
             "preco_mediano_mes_anterior": None, "variacao_percentual": None},
            {"categoria_key": "kM", "unidade_normalizada": "CAIXA", "mes": date(2026, 1, 1),
             "itens": 1, "preco_medio": 50, "preco_mediano": 50,
             "preco_mediano_mes_anterior": None, "variacao_percentual": None},
        ],
    )  # fmt: skip
    _insert(
        gold,
        mart_ranking_fornecedor_orgao,
        [
            {"orgao_key": "oA", "fornecedor_key": "f2", "itens_vencidos": 1,
             "valor_total_homologado": 500, "ranking": 2, "participacao_percentual": 33.33},
            {"orgao_key": "oA", "fornecedor_key": "f1", "itens_vencidos": 2,
             "valor_total_homologado": 1000, "ranking": 1, "participacao_percentual": 66.67},
            {"orgao_key": "oB", "fornecedor_key": "f1", "itens_vencidos": 1,
             "valor_total_homologado": 50, "ranking": 1, "participacao_percentual": 100},
        ],
    )  # fmt: skip
    _insert(
        gold,
        mart_percentil_preco_item,
        [
            {"item_key": f"i{n}", "numero_controle_pncp": f"{CNPJ_A}-1-000001/2026",
             "numero_item": n, "orgao_key": "oA", "categoria_key": "k30",
             "unidade_normalizada": "UNIDADE", "data_publicacao": date(2026, 1, 10),
             "valor_unitario_estimado": valor, "percentil_preco": percentil,
             "itens_comparaveis": 5, "acima_p90": alerta}
            for n, valor, percentil, alerta in [
                (1, 10, 0, False),
                (2, 50, 1, True),
                (3, 45, Decimal("0.9"), True),
                (4, 44, Decimal("0.9"), True),
            ]
        ],
    )  # fmt: skip
    return gold


# ------------------------------------------------------------------ sem gold


@pytest.mark.parametrize(
    "path",
    ["/categorias", "/metricas/valor-mensal", "/metricas/precos-acima-p90"],
)
def test_without_gold_schema_returns_503(api_client: TestClient, path: str) -> None:
    # nenhum dbt rodou neste banco: o schema gold não existe
    response = api_client.get(path)

    assert response.status_code == 503
    assert response.headers["content-type"] == "application/problem+json"


def test_silver_routes_work_without_gold(api_client: TestClient) -> None:
    # a falta da gold não pode derrubar as rotas da silver
    assert api_client.get("/contratacoes").status_code == 200


# ------------------------------------------------------------------ com gold


@pytest.mark.usefixtures("gold_com_dados")
def test_categorias_unclassified_first_within_each_type(api_client: TestClient) -> None:
    body = api_client.get("/categorias").json()

    assert [(c["material_ou_servico"], c["ncm_capitulo"]) for c in body] == [
        ("M", None),
        ("M", "30"),
        ("S", None),
    ]


@pytest.mark.usefixtures("gold_com_dados")
def test_valor_mensal_in_chronological_order(api_client: TestClient) -> None:
    body = api_client.get("/metricas/valor-mensal").json()

    assert [(v["mes"], v["media_movel_3m"]) for v in body] == [
        ("2026-01-01", "300.00"),
        ("2026-02-01", "150.00"),
    ]


@pytest.mark.usefixtures("gold_com_dados")
def test_preco_categoria_joins_dimension_and_filters(api_client: TestClient) -> None:
    todos = api_client.get("/metricas/preco-categoria").json()
    capitulo_30 = api_client.get("/metricas/preco-categoria", params={"categoria": "30"}).json()

    assert len(todos) == 3
    assert [(p["mes"], p["variacao_percentual"]) for p in capitulo_30] == [
        ("2026-01-01", None),
        ("2026-02-01", "10.00"),
    ]
    assert capitulo_30[0]["categoria"]["nome"] == "30 - Produtos farmacêuticos"


@pytest.mark.usefixtures("gold_com_dados")
def test_ranking_ordered_and_filtered_by_orgao(api_client: TestClient) -> None:
    todos = api_client.get("/metricas/ranking-fornecedores").json()
    so_a = api_client.get("/metricas/ranking-fornecedores", params={"orgao": CNPJ_A}).json()

    # por órgão (alfabético: "Estado B" antes de "Prefeitura A") e posição
    assert [(r["orgao_razao_social"], r["ranking"]) for r in todos] == [
        ("Estado B", 1),
        ("Prefeitura A", 1),
        ("Prefeitura A", 2),
    ]
    assert [r["fornecedor_nome"] for r in so_a] == ["Fornecedor 1", "Fornecedor 2"]


@pytest.mark.usefixtures("gold_com_dados")
def test_precos_acima_p90_only_alerts_most_expensive_first(api_client: TestClient) -> None:
    primeira = api_client.get("/metricas/precos-acima-p90", params={"tamanho_pagina": 2}).json()
    segunda = api_client.get(
        "/metricas/precos-acima-p90", params={"tamanho_pagina": 2, "pagina": 2}
    ).json()

    assert (primeira["total"], primeira["total_paginas"]) == (3, 2)
    assert [i["numero_item"] for i in primeira["itens"]] == [2, 3]
    assert [i["numero_item"] for i in segunda["itens"]] == [4]
    assert primeira["itens"][0]["contratacao_id"] == f"{CNPJ_A}-1-000001-2026"
    assert primeira["itens"][0]["orgao_razao_social"] == "Prefeitura A"


def test_money_from_gold_has_four_decimal_places(gold: Engine, api_client: TestClient) -> None:
    # bug achado na execução real: soma de quantidade x preço no dbt vinha com 8 casas
    _insert(
        gold,
        mart_valor_contratado_mensal,
        [{"mes": date(2026, 9, 1), "contratacoes": 1, "itens": 1,
          "valor_total_estimado": Decimal("148851981.78880000"),
          "media_movel_3m": Decimal("148851981.79"), "meses_na_media": 1}],
    )  # fmt: skip
    _insert(gold, dim_orgao, [{"orgao_key": "oA", "cnpj": CNPJ_A, "razao_social": "A"}])
    _insert(gold, dim_fornecedor, [{"fornecedor_key": "f1", "documento": "1", "nome": "F"}])
    _insert(
        gold,
        mart_ranking_fornecedor_orgao,
        [{"orgao_key": "oA", "fornecedor_key": "f1", "itens_vencidos": 1,
          "valor_total_homologado": Decimal("10.12345678"), "ranking": 1,
          "participacao_percentual": 100}],
    )  # fmt: skip

    mensal = api_client.get("/metricas/valor-mensal").json()[0]
    ranking = api_client.get("/metricas/ranking-fornecedores").json()[0]

    assert mensal["valor_total_estimado"] == "148851981.7888"
    assert ranking["valor_total_homologado"] == "10.1235"
