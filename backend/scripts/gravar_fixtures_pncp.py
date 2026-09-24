"""Grava respostas REAIS do PNCP em tests/fixtures/pncp/ para os testes do cliente.

Uso (manual, nunca no CI):  make pncp-fixtures

Os testes nunca acessam a rede: usam estes arquivos. Rode de novo só se a API do PNCP
mudar de formato. As listas são enxugadas (poucos registros) para os arquivos ficarem
pequenos; o conteúdo de cada registro é mantido exatamente como veio.
"""

import json
from pathlib import Path
from typing import Any

import httpx
import structlog

CONSULTA = "https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao"
API = "https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{seq}"
OUT = Path(__file__).parents[1] / "tests" / "fixtures" / "pncp"
# um dia antigo: as contratações já têm resultado homologado
PARAMS = {"dataInicial": "20250310", "dataFinal": "20250314", "codigoModalidadeContratacao": 6,
          "uf": "CE", "pagina": 1, "tamanhoPagina": 50}  # fmt: skip

log = structlog.get_logger()


def _get(client: httpx.Client, url: str, **params: Any) -> Any:
    response = client.get(url, params=params)
    response.raise_for_status()
    return response.json()


def _save(name: str, content: Any) -> None:
    path = OUT / name
    path.write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log.info("fixture_gravada", arquivo=str(path.relative_to(OUT.parents[2])))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        page = _get(client, CONSULTA, **PARAMS)
        # escolhe uma contratação com itens homologados e com edital publicado
        for contratacao in page["data"]:
            base = API.format(
                cnpj=contratacao["orgaoEntidade"]["cnpj"],
                ano=contratacao["anoCompra"],
                seq=contratacao["sequencialCompra"],
            )
            itens = _get(client, f"{base}/itens")
            arquivos = _get(client, f"{base}/arquivos")
            com_resultado = [i for i in itens if i.get("temResultado")]
            if com_resultado and any(a.get("tipoDocumentoId") == 2 for a in arquivos):
                break
        else:
            raise SystemExit("nenhuma contratação com resultado e edital no período")

        numero = com_resultado[0]["numeroItem"]
        resultados = _get(client, f"{base}/itens/{numero}/resultados")

    page["data"] = [contratacao, *[c for c in page["data"] if c is not contratacao][:2]]
    _save("publicacao_pagina.json", page)
    _save("itens.json", itens[:3] if com_resultado[0] in itens[:3] else [com_resultado[0]])
    _save("resultados.json", resultados)
    _save("arquivos.json", arquivos)


if __name__ == "__main__":
    main()
