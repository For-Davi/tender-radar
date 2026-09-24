"""Testes dos value objects de documento: Cnpj e Cpf."""

import pytest

from radar.domain.errors import InvalidValueError
from radar.domain.value_objects import Cnpj, Cpf

# ------------------------------------------------------------------ CNPJ


@pytest.mark.parametrize(
    "raw",
    [
        "11222333000181",  # só dígitos
        "11.222.333/0001-81",  # com máscara
        " 11.222.333/0001-81 ",  # com espaços nas pontas
    ],
)
def test_cnpj_valid_with_or_without_mask(raw: str) -> None:
    assert Cnpj(raw).value == "11222333000181"


def test_cnpj_alphanumeric_is_valid() -> None:
    # exemplo oficial da Receita Federal para o CNPJ alfanumérico (IN RFB 2.229/2024)
    assert Cnpj("12.ABC.345/01DE-35").value == "12ABC34501DE35"


def test_cnpj_alphanumeric_accepts_lowercase() -> None:
    assert Cnpj("12abc34501de35").value == "12ABC34501DE35"


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        ("11222333000182", "dígito verificador errado"),
        ("1122233300018", "13 caracteres"),
        ("112223330001810", "15 caracteres"),
        ("00000000000000", "todos os caracteres iguais"),
        ("11111111111111", "todos os caracteres iguais"),
        ("12ABC34501DE3A", "letra no dígito verificador"),
        ("11.222.333/0001#81", "caractere não permitido"),
        ("", "vazio"),
    ],
)
def test_cnpj_invalid_is_rejected(raw: str, reason: str) -> None:
    with pytest.raises(InvalidValueError, match="CNPJ inválido"):
        Cnpj(raw)


def test_cnpj_masked_and_unmasked_are_equal() -> None:
    assert Cnpj("11.222.333/0001-81") == Cnpj("11222333000181")


def test_cnpj_formatted() -> None:
    assert Cnpj("11222333000181").formatted() == "11.222.333/0001-81"


def test_cnpj_is_immutable() -> None:
    cnpj = Cnpj("11222333000181")

    with pytest.raises(AttributeError):
        cnpj.value = "00000000000000"  # type: ignore[misc]


# ------------------------------------------------------------------ CPF


@pytest.mark.parametrize("raw", ["52998224725", "529.982.247-25"])
def test_cpf_valid_with_or_without_mask(raw: str) -> None:
    assert Cpf(raw).value == "52998224725"


@pytest.mark.parametrize(
    "raw",
    ["52998224724", "5299822472", "11111111111", "529.982.247-2X", ""],
)
def test_cpf_invalid_is_rejected(raw: str) -> None:
    with pytest.raises(InvalidValueError, match="CPF inválido"):
        Cpf(raw)


def test_cpf_formatted() -> None:
    assert Cpf("52998224725").formatted() == "529.982.247-25"
