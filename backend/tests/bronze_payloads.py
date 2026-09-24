"""Payloads da bronze para os testes do bronze -> silver, montados a partir das
respostas REAIS do PNCP gravadas em `tests/fixtures/pncp/` (o mesmo formato que a
ingestão da Etapa 02 grava no Mongo).

Os testes partem do payload real e mudam só o campo que interessa.
"""

import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from radar.ports.bronze import BronzeVersion
from radar.ports.contratacoes_source import JsonDict
from radar.services.ingestao import payload_hash

_FIXTURES = Path(__file__).parent / "fixtures" / "pncp"
NUMERO_FIXTURE = "07954480000179-1-001878/2025"
CNPJ_ORGAO_FIXTURE = "07954480000179"
CNPJ_FORNECEDOR_FIXTURE = "12561319000175"


def _fixture(name: str) -> Any:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


def fixture_payload() -> JsonDict:
    """Contratação real: 3 itens; só o item 1 tem resultado gravado na fixture."""
    return {
        "contratacao": _fixture("publicacao_pagina.json")["data"][0],
        "itens": _fixture("itens.json"),
        "resultados": {"1": _fixture("resultados.json")},
        "arquivos": _fixture("arquivos.json"),
    }


def payload_with_numero(sequencial: int) -> JsonDict:
    """Cópia da fixture como se fosse outra contratação do mesmo órgão."""
    payload = copy.deepcopy(fixture_payload())
    payload["contratacao"]["numeroControlePNCP"] = f"{CNPJ_ORGAO_FIXTURE}-1-{sequencial:06d}/2025"
    payload["contratacao"]["sequencialCompra"] = sequencial
    return payload


def make_version(
    payload: JsonDict | None = None,
    *,
    vigente_desde: datetime | None = None,
) -> BronzeVersion:
    payload = fixture_payload() if payload is None else payload
    contratacao = payload.get("contratacao")
    numero = contratacao.get("numeroControlePNCP") if isinstance(contratacao, dict) else None
    return BronzeVersion(
        numero_controle_pncp=str(numero),
        hash=payload_hash(payload),
        payload=payload,
        vigente_desde=vigente_desde or datetime(2026, 9, 24, 12, 0, tzinfo=UTC),
    )
