"""/contratacoes e /orgaos contra um Postgres real: os filtros, a ordenação e a
paginação são SQL de verdade.

Cenário (gravado pelos repositórios da Etapa 01):

| seq | órgão | UF | publicação (UTC)  | dia em Brasília | valor   | NCM do item |
|-----|-------|----|-------------------|-----------------|---------|-------------|
| 1   | A     | CE | 10/03 12:00       | 10/03           | 1000    | 30049099    |
| 2   | A     | CE | 11/03 02:30       | 10/03 (23:30!)  | 5000    | 90181990    |
| 3   | B     | SP | 12/03 12:00       | 12/03           | sigilo  | (nenhum)    |
| 4   | B     | SP | 12/03 12:00 (=3)  | 12/03           | 200     | 30021500    |

O órgão C não tem contratação.
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from radar.adapters.postgres.repositories import (
    SqlContratacaoRepository,
    SqlFornecedorRepository,
    SqlOrgaoRepository,
)
from radar.domain.value_objects import Cnpj, Dinheiro
from tests.factories import (
    CNPJ_FORNECEDOR,
    CNPJ_ORGAO,
    make_contratacao,
    make_fornecedor,
    make_item,
    make_orgao,
)

CNPJ_B = "07954480000179"
CNPJ_C = "00000000000191"


def _numero(cnpj: str, seq: int) -> str:
    return f"{cnpj}-1-{seq:06d}/2025"


def _id(cnpj: str, seq: int) -> str:
    return f"{cnpj}-1-{seq:06d}-2025"


@pytest.fixture
def cenario(session: Session) -> Iterator[None]:
    orgaos = SqlOrgaoRepository(session)
    orgaos.upsert(make_orgao())  # A: "Prefeitura Municipal de Exemplo"
    orgaos.upsert(make_orgao(cnpj=Cnpj(CNPJ_B), razao_social="Governo do Estado B"))
    orgaos.upsert(make_orgao(cnpj=Cnpj(CNPJ_C), razao_social="Autarquia C"))
    SqlFornecedorRepository(session).upsert(make_fornecedor())

    def contratacao(seq: int, cnpj: str, uf: str, publicacao: datetime, **extra: Any) -> None:
        SqlContratacaoRepository(session).add(
            make_contratacao(
                numero_controle_pncp=_numero(cnpj, seq),
                orgao_cnpj=Cnpj(cnpj),
                uf=uf,
                data_publicacao=publicacao,
                objeto=f"Objeto {seq}",
                **extra,
            )
        )

    contratacao(
        1,
        CNPJ_ORGAO,
        "CE",
        datetime(2025, 3, 10, 12, 0, tzinfo=UTC),
        valor_total_estimado=Dinheiro.de("1000"),
        itens=[make_item(ncm_nbs="30049099")],
    )
    contratacao(
        2,
        CNPJ_ORGAO,
        "CE",
        # 23:30 de 10/03 em Brasília (UTC-3)
        datetime(2025, 3, 11, 2, 30, tzinfo=UTC),
        valor_total_estimado=Dinheiro.de("5000"),
        itens=[
            make_item(numero_item=1, ncm_nbs="90181990"),
            make_item(
                numero_item=2,
                fornecedor_documento=CNPJ_FORNECEDOR,
                valor_unitario_homologado=Dinheiro.de("4500"),
            ),
        ],
    )
    contratacao(
        3,
        CNPJ_B,
        "SP",
        datetime(2025, 3, 12, 12, 0, tzinfo=UTC),
        valor_total_estimado=None,
        itens=[make_item(ncm_nbs=None, valor_unitario_estimado=None)],
    )
    contratacao(
        4,
        CNPJ_B,
        "SP",
        datetime(2025, 3, 12, 12, 0, tzinfo=UTC),  # empate de data com a 3
        valor_total_estimado=Dinheiro.de("200"),
        itens=[make_item(ncm_nbs="30021500")],
    )
    session.commit()
    yield


def _objetos(client: TestClient, **params: Any) -> list[str]:
    response = client.get("/contratacoes", params=params)
    assert response.status_code == 200, response.text
    return [item["objeto"] for item in response.json()["itens"]]


pytestmark = pytest.mark.usefixtures("cenario")


# ------------------------------------------------------------------ filtros


def test_without_filters_newest_first_with_stable_tiebreak(api_client: TestClient) -> None:
    # 3 e 4 têm a mesma data: o id decide (a 4 foi gravada depois)
    assert _objetos(api_client) == ["Objeto 4", "Objeto 3", "Objeto 2", "Objeto 1"]


@pytest.mark.parametrize(
    ("params", "esperados"),
    [
        ({"uf": "CE"}, ["Objeto 2", "Objeto 1"]),
        ({"uf": "RJ"}, []),
        ({"orgao": "07.954.480/0001-79"}, ["Objeto 4", "Objeto 3"]),
        ({"orgao": CNPJ_C}, []),
        # alguma contratação com item do capítulo 30 (uma de cada órgão)
        ({"categoria": "30"}, ["Objeto 4", "Objeto 1"]),
        ({"categoria": "90"}, ["Objeto 2"]),
        # a 2 foi publicada às 23:30 de 10/03 em Brasília: é do dia 10, não do 11
        ({"data_fim": "2025-03-10"}, ["Objeto 2", "Objeto 1"]),
        ({"data_inicio": "2025-03-11"}, ["Objeto 4", "Objeto 3"]),
        ({"data_inicio": "2025-03-10", "data_fim": "2025-03-10"}, ["Objeto 2", "Objeto 1"]),
        # sigiloso (valor nulo) nunca entra num filtro de valor
        ({"valor_min": "1000"}, ["Objeto 2", "Objeto 1"]),
        ({"valor_max": "1000"}, ["Objeto 4", "Objeto 1"]),
        ({"valor_min": "0"}, ["Objeto 4", "Objeto 2", "Objeto 1"]),
    ],
)
def test_each_filter(api_client: TestClient, params: dict[str, str], esperados: list[str]) -> None:
    assert _objetos(api_client, **params) == esperados


def test_combined_filters(api_client: TestClient) -> None:
    params = {"uf": "CE", "categoria": "30", "valor_max": "1000", "data_fim": "2025-03-10"}

    assert _objetos(api_client, **params) == ["Objeto 1"]


def test_total_counts_all_matching_rows(api_client: TestClient) -> None:
    body = api_client.get("/contratacoes", params={"uf": "SP", "tamanho_pagina": 1}).json()

    assert (body["total"], body["total_paginas"], len(body["itens"])) == (2, 2, 1)


# ------------------------------------------------------------------ ordenação


@pytest.mark.parametrize(
    ("ordenar", "esperados"),
    [
        ("data_publicacao", ["Objeto 1", "Objeto 2", "Objeto 3", "Objeto 4"]),
        # sigiloso (3) sempre por último, nos dois sentidos
        ("-valor_total_estimado", ["Objeto 2", "Objeto 1", "Objeto 4", "Objeto 3"]),
        ("valor_total_estimado", ["Objeto 4", "Objeto 1", "Objeto 2", "Objeto 3"]),
    ],
)
def test_ordering(api_client: TestClient, ordenar: str, esperados: list[str]) -> None:
    assert _objetos(api_client, ordenar=ordenar) == esperados


# ------------------------------------------------------------------ paginação


def test_pages_cover_everything_once(api_client: TestClient) -> None:
    paginas = [_objetos(api_client, pagina=n, tamanho_pagina=3) for n in (1, 2, 3)]

    assert [len(p) for p in paginas] == [3, 1, 0]  # primeira, última, além da última
    todos = [objeto for pagina in paginas for objeto in pagina]
    assert sorted(todos) == ["Objeto 1", "Objeto 2", "Objeto 3", "Objeto 4"]


def test_page_boundary_inside_a_tie_is_stable(api_client: TestClient) -> None:
    # 3 e 4 empatam na data; com tamanho 1, cada uma cai numa página, sem repetir
    primeira = _objetos(api_client, pagina=1, tamanho_pagina=1)
    segunda = _objetos(api_client, pagina=2, tamanho_pagina=1)

    assert (primeira, segunda) == (["Objeto 4"], ["Objeto 3"])


# ------------------------------------------------------------------ campos e detalhe


def test_list_item_fields_from_database(api_client: TestClient) -> None:
    item = api_client.get("/contratacoes", params={"categoria": "90"}).json()["itens"][0]

    assert item["id"] == _id(CNPJ_ORGAO, 2)
    assert item["orgao"] == {"cnpj": CNPJ_ORGAO, "razao_social": "Prefeitura Municipal de Exemplo"}
    assert item["valor_total_estimado"] == "5000.0000"
    assert item["data_publicacao"] == "2025-03-11T02:30:00Z"
    assert item["total_itens"] == 2


def test_detail_with_items_and_winner(api_client: TestClient) -> None:
    response = api_client.get(f"/contratacoes/{_id(CNPJ_ORGAO, 2)}")

    assert response.status_code == 200
    itens = response.json()["itens"]
    assert [item["numero_item"] for item in itens] == [1, 2]
    assert itens[0]["vencedor"] is None
    assert itens[1]["vencedor"]["documento"] == CNPJ_FORNECEDOR
    assert itens[1]["valor_unitario_homologado"] == "4500.0000"
    # 10 x 4999.90
    assert itens[1]["valor_total_estimado"] == "49999.0000"


def test_detail_of_secret_contratacao(api_client: TestClient) -> None:
    body = api_client.get(f"/contratacoes/{_id(CNPJ_B, 3)}").json()

    assert body["valor_total_estimado"] is None
    assert body["itens"][0]["valor_unitario_estimado"] is None
    assert body["itens"][0]["valor_total_estimado"] is None


def test_detail_not_found(api_client: TestClient) -> None:
    response = api_client.get(f"/contratacoes/{_id(CNPJ_ORGAO, 999)}")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"


# ------------------------------------------------------------------ órgãos


def test_orgaos_alphabetical_with_counts(api_client: TestClient) -> None:
    body = api_client.get("/orgaos").json()

    assert [(o["razao_social"], o["total_contratacoes"]) for o in body["itens"]] == [
        ("Autarquia C", 0),
        ("Governo do Estado B", 2),
        ("Prefeitura Municipal de Exemplo", 2),
    ]
    assert body["itens"][0]["esfera_nome"] == "Municipal"


def test_orgaos_by_uf_only_those_with_contratacoes_there(api_client: TestClient) -> None:
    body = api_client.get("/orgaos", params={"uf": "SP"}).json()

    assert body["total"] == 1
    assert [(o["cnpj"], o["total_contratacoes"]) for o in body["itens"]] == [(CNPJ_B, 2)]


def test_orgaos_pagination(api_client: TestClient) -> None:
    body = api_client.get("/orgaos", params={"pagina": 2, "tamanho_pagina": 2}).json()

    assert (body["total"], body["total_paginas"]) == (3, 2)
    assert [o["razao_social"] for o in body["itens"]] == ["Prefeitura Municipal de Exemplo"]
