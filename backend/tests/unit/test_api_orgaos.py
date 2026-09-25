"""Testes de /orgaos com o port trocado por um fake."""

import pytest
from fastapi.testclient import TestClient

from radar.ports.consultas import PaginaPedido
from tests.fakes_consultas import FakeOrgaoQueries, make_orgao_resumo


def test_list_orgaos(api: TestClient, fake_orgaos: FakeOrgaoQueries) -> None:
    fake_orgaos.orgaos = [make_orgao_resumo(1)]

    response = api.get("/orgaos")

    assert response.status_code == 200
    assert response.json()["itens"] == [
        {
            "cnpj": "00000000000001",
            "razao_social": "Órgão 1",
            "esfera": "E",
            "esfera_nome": "Estadual",
            "poder": "E",
            "poder_nome": "Executivo",
            "total_contratacoes": 1,
        }
    ]
    assert fake_orgaos.chamadas == [(None, PaginaPedido(1, 20))]


def test_uf_filter_and_pagination_reach_the_port(
    api: TestClient, fake_orgaos: FakeOrgaoQueries
) -> None:
    api.get("/orgaos", params={"uf": "sp", "pagina": 2, "tamanho_pagina": 50})

    assert fake_orgaos.chamadas == [("SP", PaginaPedido(2, 50))]


@pytest.mark.parametrize(
    ("pagina", "quantidade"),
    [(1, 2), (2, 1), (3, 0)],  # primeira, última (incompleta) e além da última
)
def test_pagination(
    api: TestClient, fake_orgaos: FakeOrgaoQueries, pagina: int, quantidade: int
) -> None:
    fake_orgaos.orgaos = [make_orgao_resumo(n) for n in range(1, 4)]

    body = api.get("/orgaos", params={"pagina": pagina, "tamanho_pagina": 2}).json()

    assert (body["total"], body["total_paginas"], len(body["itens"])) == (3, 2, quantidade)


@pytest.mark.parametrize(
    ("query", "campo"),
    [({"uf": "BR"}, "query.uf"), ({"pagina": "-1"}, "query.pagina")],
)
def test_invalid_params_return_422(api: TestClient, query: dict[str, str], campo: str) -> None:
    response = api.get("/orgaos", params=query)

    assert response.status_code == 422
    assert response.json()["erros"][0]["campo"] == campo
