"""Testes do cliente do PNCP. Sem rede: o `respx` intercepta as chamadas do httpx."""

import json
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from radar.adapters.pncp.client import PncpClient
from radar.ports.contratacoes_source import (
    ContratacaoRef,
    DocumentTooLargeError,
    SourceRequestError,
    SourceSchemaError,
    SourceUnavailableError,
)

FIXTURES = Path(__file__).parents[1] / "fixtures" / "pncp"
CONSULTA = "https://pncp.test/api/consulta"
API = "https://pncp.test/api/pncp"
PUBLICACAO = f"{CONSULTA}/v1/contratacoes/publicacao"
REF = ContratacaoRef("07954480000179-1-001878/2025", "07954480000179", 2025, 1878)
COMPRA = f"{API}/v1/orgaos/07954480000179/compras/2025/1878"


def _fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeTime:
    """Relógio falso: `sleep` só avança o tempo, sem esperar de verdade."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def fake_time() -> FakeTime:
    return FakeTime()


@pytest.fixture
def client(fake_time: FakeTime) -> Iterator[PncpClient]:
    with httpx.Client() as http:
        yield PncpClient(
            http,
            consulta_url=CONSULTA,
            api_url=API,
            max_attempts=3,
            min_interval_seconds=0.0,
            max_download_bytes=1000,
            sleep=fake_time.sleep,
            monotonic=fake_time.monotonic,
        )


def _page(records: list[Any], numero: int, total: int) -> dict[str, Any]:
    return {
        "data": records,
        "totalRegistros": 99,
        "totalPaginas": total,
        "numeroPagina": numero,
        "paginasRestantes": total - numero,
        "empty": not records,
    }


def _list(client: PncpClient) -> list[str]:
    items = client.list_contratacoes(date(2025, 3, 10), date(2025, 3, 14), modalidade=6, uf="CE")
    return [c.ref.numero_controle_pncp for c in items]


# ------------------------------------------------------------------ parsing


@respx.mock
def test_parses_recorded_real_response(client: PncpClient) -> None:
    page = _fixture("publicacao_pagina.json") | {"paginasRestantes": 0}
    route = respx.get(PUBLICACAO).respond(json=page)

    result = list(
        client.list_contratacoes(date(2025, 3, 10), date(2025, 3, 14), modalidade=6, uf="CE")
    )

    assert len(result) == 3
    assert result[0].ref == REF
    assert result[0].payload == page["data"][0]  # o bruto vai intacto para a bronze
    params = route.calls[0].request.url.params
    assert params["dataInicial"] == "20250310"
    assert params["dataFinal"] == "20250314"
    assert params["codigoModalidadeContratacao"] == "6"
    assert params["uf"] == "CE"
    assert params["tamanhoPagina"] == "50"


@respx.mock
def test_extra_fields_are_kept_in_payload(client: PncpClient) -> None:
    record = _fixture("publicacao_pagina.json")["data"][0] | {"campoNovoDoPncp": "x"}
    respx.get(PUBLICACAO).respond(json=_page([record], 1, 1))

    (result,) = client.list_contratacoes(date(2025, 3, 10), date(2025, 3, 10), 6, "CE")

    assert result.payload["campoNovoDoPncp"] == "x"


@respx.mock
def test_missing_required_field_gives_readable_error(client: PncpClient) -> None:
    record = _fixture("publicacao_pagina.json")["data"][0]
    del record["numeroControlePNCP"]
    respx.get(PUBLICACAO).respond(json=_page([record], 1, 1))

    with pytest.raises(SourceSchemaError, match=r"numeroControlePNCP.*(obrigatório|required)"):
        _list(client)


@respx.mock
def test_wrong_type_gives_readable_error_with_field_path(client: PncpClient) -> None:
    record = _fixture("publicacao_pagina.json")["data"][0]
    record["orgaoEntidade"]["cnpj"] = None
    respx.get(PUBLICACAO).respond(json=_page([record], 1, 1))

    with pytest.raises(SourceSchemaError, match=r"orgaoEntidade\.cnpj"):
        _list(client)


@respx.mock
def test_invalid_json_gives_schema_error(client: PncpClient) -> None:
    respx.get(PUBLICACAO).respond(text="<html>manutenção</html>")

    with pytest.raises(SourceSchemaError, match="JSON"):
        _list(client)


@respx.mock
def test_items_results_and_documents(client: PncpClient) -> None:
    respx.get(f"{COMPRA}/itens").respond(json=_fixture("itens.json"))
    respx.get(f"{COMPRA}/itens/1/resultados").respond(json=_fixture("resultados.json"))
    respx.get(f"{COMPRA}/arquivos").respond(json=_fixture("arquivos.json"))

    itens = client.get_itens(REF)
    resultados = client.get_resultados(REF, 1)
    (documento,) = client.get_documentos(REF)

    assert [(i.numero_item, i.tem_resultado) for i in itens] == [(1, True), (2, True), (3, True)]
    assert resultados[0]["niFornecedor"] == "12561319000175"
    assert documento.eh_edital
    assert documento.sequencial_documento == 1
    assert documento.url.endswith("/arquivos/1")


@respx.mock
def test_non_edital_document_is_flagged(client: PncpClient) -> None:
    arquivo = _fixture("arquivos.json")[0] | {"tipoDocumentoId": 16, "tipoDocumentoNome": "Outros"}
    respx.get(f"{COMPRA}/arquivos").respond(json=[arquivo])

    (documento,) = client.get_documentos(REF)

    assert not documento.eh_edital


@respx.mock
def test_empty_lists_return_204(client: PncpClient) -> None:
    # o PNCP responde 204 (sem corpo) quando não há resultados/arquivos
    respx.get(f"{COMPRA}/arquivos").respond(status_code=204)

    assert client.get_documentos(REF) == []


# ------------------------------------------------------------------ paginação


@respx.mock
def test_pagination_walks_all_pages_and_stops_at_last(client: PncpClient) -> None:
    record = _fixture("publicacao_pagina.json")["data"][0]

    def page_for(request: httpx.Request) -> httpx.Response:
        numero = int(request.url.params["pagina"])
        other = record | {"numeroControlePNCP": f"07954480000179-1-00000{numero}/2025"}
        return httpx.Response(200, json=_page([other], numero, 3))

    route = respx.get(PUBLICACAO).mock(side_effect=page_for)

    numeros = _list(client)

    assert numeros == [f"07954480000179-1-00000{n}/2025" for n in (1, 2, 3)]
    assert route.call_count == 3  # não pede a página 4


@respx.mock
def test_pagination_stops_on_204(client: PncpClient) -> None:
    record = _fixture("publicacao_pagina.json")["data"][0]
    route = respx.get(PUBLICACAO).mock(
        side_effect=[httpx.Response(200, json=_page([record], 1, 5)), httpx.Response(204)]
    )

    assert len(_list(client)) == 1
    assert route.call_count == 2


@respx.mock
def test_no_results_returns_empty(client: PncpClient) -> None:
    respx.get(PUBLICACAO).respond(status_code=204)

    assert _list(client) == []


# ------------------------------------------------------------------ retry


@respx.mock
@pytest.mark.parametrize("status", [500, 502, 503, 504, 429])
def test_retries_transient_errors_then_succeeds(
    client: PncpClient, fake_time: FakeTime, status: int
) -> None:
    route = respx.get(f"{COMPRA}/itens").mock(
        side_effect=[httpx.Response(status), httpx.Response(200, json=[])]
    )

    assert client.get_itens(REF) == []
    assert route.call_count == 2
    assert len(fake_time.sleeps) == 1  # esperou antes da 2ª tentativa


@respx.mock
def test_retries_timeout(client: PncpClient) -> None:
    route = respx.get(f"{COMPRA}/itens").mock(
        side_effect=[httpx.ReadTimeout("lento"), httpx.Response(200, json=[])]
    )

    assert client.get_itens(REF) == []
    assert route.call_count == 2


@respx.mock
def test_respects_retry_after_header(client: PncpClient, fake_time: FakeTime) -> None:
    respx.get(f"{COMPRA}/itens").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "7"}),
            httpx.Response(200, json=[]),
        ]
    )

    client.get_itens(REF)

    assert fake_time.sleeps == [7.0]


@respx.mock
def test_backoff_grows_between_attempts(client: PncpClient, fake_time: FakeTime) -> None:
    respx.get(f"{COMPRA}/itens").mock(
        side_effect=[httpx.Response(503), httpx.Response(503), httpx.Response(200, json=[])]
    )

    client.get_itens(REF)

    assert len(fake_time.sleeps) == 2
    assert fake_time.sleeps[1] > fake_time.sleeps[0]


@respx.mock
def test_gives_up_after_max_attempts_with_clear_error(client: PncpClient) -> None:
    route = respx.get(f"{COMPRA}/itens").respond(status_code=503)

    with pytest.raises(SourceUnavailableError, match=r"3 tentativas.*503"):
        client.get_itens(REF)

    assert route.call_count == 3


@respx.mock
@pytest.mark.parametrize("status", [400, 404, 422])
def test_does_not_retry_client_errors(client: PncpClient, status: int) -> None:
    route = respx.get(f"{COMPRA}/itens").respond(status_code=status, text="pedido inválido")

    with pytest.raises(SourceRequestError, match=str(status)):
        client.get_itens(REF)

    assert route.call_count == 1  # repetir um 4xx só repetiria o erro


# ------------------------------------------------------------------ download e ritmo


@respx.mock
def test_download_returns_bytes_following_redirect(client: PncpClient) -> None:
    respx.get("https://pncp.test/arquivo/1").respond(
        status_code=302, headers={"Location": "https://pncp.test/real/1"}
    )
    respx.get("https://pncp.test/real/1").respond(content=b"%PDF-1.7 conteudo")

    assert client.download("https://pncp.test/arquivo/1") == b"%PDF-1.7 conteudo"


@respx.mock
def test_download_over_limit_is_rejected(client: PncpClient) -> None:
    respx.get("https://pncp.test/arquivo/1").respond(content=b"x" * 1001)

    with pytest.raises(DocumentTooLargeError, match="1000"):
        client.download("https://pncp.test/arquivo/1")


@respx.mock
def test_min_interval_between_requests(fake_time: FakeTime) -> None:
    respx.get(f"{COMPRA}/itens").respond(json=[])
    with httpx.Client() as http:
        client = PncpClient(
            http,
            consulta_url=CONSULTA,
            api_url=API,
            max_attempts=1,
            min_interval_seconds=0.5,
            max_download_bytes=1000,
            sleep=fake_time.sleep,
            monotonic=fake_time.monotonic,
        )
        client.get_itens(REF)
        client.get_itens(REF)  # imediatamente depois: precisa esperar 0,5 s

    assert fake_time.sleeps == [0.5]
