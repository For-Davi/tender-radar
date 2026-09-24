"""Regras de limpeza do bronze -> silver: cada regra com suas bordas."""

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from radar.pipelines.normalizacao import (
    BRASILIA,
    normalizar_categoria,
    normalizar_texto,
    para_datetime,
    para_decimal,
    para_decimal_opcional,
    texto_obrigatorio,
)

# ------------------------------------------------------------------ dinheiro / números


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1.234,56", Decimal("1234.56")),  # formato brasileiro
        ("1.234.567,8", Decimal("1234567.8")),
        ("0,0345", Decimal("0.0345")),
        ("1234.56", Decimal("1234.56")),  # sem vírgula: ponto é decimal (padrão JSON)
        ("  42  ", Decimal("42")),
        (1234, Decimal("1234")),
        (Decimal("7.5"), Decimal("7.5")),
    ],
)
def test_para_decimal_accepts_known_formats(raw: object, expected: Decimal) -> None:
    assert para_decimal(raw) == expected


def test_para_decimal_keeps_what_the_api_sent_for_floats() -> None:
    # Decimal(0.1) seria 0.1000000000000000055511151231257827...; via str fica 0.1
    assert para_decimal(0.1) == Decimal("0.1")
    assert para_decimal(29095.0775) == Decimal("29095.0775")


@pytest.mark.parametrize(
    "raw",
    ["", "   ", "abc", "1,2,3", "R$ 10", "NaN", "Infinity", float("nan"), float("inf"), True, None],
)
def test_para_decimal_rejects_garbage(raw: object) -> None:
    with pytest.raises(ValueError, match="número"):
        para_decimal(raw)


def test_para_decimal_opcional_keeps_none() -> None:
    assert para_decimal_opcional(None) is None
    assert para_decimal_opcional("2,5") == Decimal("2.5")


# ------------------------------------------------------------------ datas


def test_naive_datetime_is_brasilia_time() -> None:
    result = para_datetime("2025-03-10T07:15:44")

    assert result == datetime(2025, 3, 10, 7, 15, 44, tzinfo=BRASILIA)
    assert result.astimezone(UTC) == datetime(2025, 3, 10, 10, 15, 44, tzinfo=UTC)


def test_datetime_with_offset_is_kept() -> None:
    result = para_datetime("2025-03-10T07:15:44+00:00")

    assert result == datetime(2025, 3, 10, 7, 15, 44, tzinfo=UTC)


def test_datetime_with_z_suffix() -> None:
    assert para_datetime("2025-03-10T07:15:44Z") == datetime(2025, 3, 10, 7, 15, 44, tzinfo=UTC)


def test_datetime_object_naive_and_aware() -> None:
    aware = datetime(2025, 1, 1, tzinfo=timezone(timedelta(hours=-5)))

    assert para_datetime(aware) is aware
    assert para_datetime(datetime(2025, 1, 1)).tzinfo == BRASILIA


@pytest.mark.parametrize("raw", ["2025-02-30T10:00:00", "10/03/2025", "", "ontem", 20250310, None])
def test_invalid_datetime_is_rejected(raw: object) -> None:
    with pytest.raises(ValueError, match="data"):
        para_datetime(raw)


# ------------------------------------------------------------------ textos


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Câmara   conservação \n", "Câmara conservação"),
        ("EMBALAGEM 1.0 UNIDADE ", "EMBALAGEM 1.0 UNIDADE"),
        ("   ", None),
        ("", None),
        (None, None),
    ],
)
def test_normalizar_texto(raw: object, expected: str | None) -> None:
    assert normalizar_texto(raw) == expected


def test_normalizar_texto_rejects_non_text() -> None:
    with pytest.raises(ValueError, match="texto"):
        normalizar_texto(123)


def test_texto_obrigatorio_rejects_blank() -> None:
    assert texto_obrigatorio(" Fortaleza ") == "Fortaleza"
    with pytest.raises(ValueError, match="vazio"):
        texto_obrigatorio("   ")


@pytest.mark.parametrize("placeholder", ["Não se aplica", "NÃO SE APLICA", " nao se aplica ", "-"])
def test_categoria_placeholders_become_none(placeholder: str) -> None:
    # "Não se aplica" não é uma categoria: tratar como categoria criaria um grupo falso
    assert normalizar_categoria(placeholder) is None


def test_categoria_real_is_kept() -> None:
    assert normalizar_categoria("  Material de  consumo ") == "Material de consumo"
