"""Testes da conversão entre o número de controle do PNCP e o id público da API."""

import pytest

from radar.api.ids import para_id_publico, para_numero_controle
from radar.domain.errors import InvalidValueError

NUMERO = "13183513000127-1-000173/2025"
ID_PUBLICO = "13183513000127-1-000173-2025"


def test_numero_controle_to_public_id() -> None:
    assert para_id_publico(NUMERO) == ID_PUBLICO


def test_public_id_to_numero_controle() -> None:
    assert para_numero_controle(ID_PUBLICO) == NUMERO


def test_roundtrip_with_alphanumeric_cnpj() -> None:
    numero = "12ABC34501DE35-1-000001/2026"

    assert para_numero_controle(para_id_publico(numero)) == numero


@pytest.mark.parametrize(
    "invalido",
    [
        "",
        NUMERO,  # com barra: não é o formato público
        "13183513000127-1-000173-25",  # ano com 2 dígitos
        "13183513000127-2-000173-2025",  # tipo 2 não é contratação
        "1318351300012-1-000173-2025",  # CNPJ curto
        "13183513000127-1-173-2025",  # sequencial sem zeros
        "13183513000127-1-000173-2025-x",
    ],
)
def test_invalid_public_id_raises(invalido: str) -> None:
    with pytest.raises(InvalidValueError, match="id de contratação inválido"):
        para_numero_controle(invalido)
