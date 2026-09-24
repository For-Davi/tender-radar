"""Testes do value object Dinheiro (Decimal, 4 casas, sem float)."""

from decimal import Decimal

import pytest

from radar.domain.errors import InvalidValueError
from radar.domain.value_objects import Dinheiro


def test_no_floating_point_error() -> None:
    # com float: 0.1 + 0.2 == 0.30000000000000004
    assert Dinheiro.de("0.1") + Dinheiro.de("0.2") == Dinheiro.de("0.3")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1234.56", Decimal("1234.5600")),
        (10, Decimal("10.0000")),
        (Decimal("0.0345"), Decimal("0.0345")),
        ("  7.5 ", Decimal("7.5000")),
    ],
)
def test_accepts_str_int_and_decimal(raw: str | int | Decimal, expected: Decimal) -> None:
    assert Dinheiro.de(raw).valor == expected


def test_rejects_float() -> None:
    with pytest.raises(InvalidValueError, match="float"):
        Dinheiro.de(0.1)  # type: ignore[arg-type]


def test_rejects_bool() -> None:
    # bool é subclasse de int em Python: Dinheiro.de(True) viraria R$ 1 sem esta regra
    with pytest.raises(InvalidValueError):
        Dinheiro.de(True)


@pytest.mark.parametrize("raw", ["abc", "1,234.56", "NaN", "Infinity", ""])
def test_rejects_invalid_text(raw: str) -> None:
    with pytest.raises(InvalidValueError):
        Dinheiro.de(raw)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0.00005", Decimal("0.0000")),  # 5 exato: arredonda para o par (0)
        ("0.00015", Decimal("0.0002")),  # 5 exato: arredonda para o par (2)
        ("0.00016", Decimal("0.0002")),
        ("0.00014", Decimal("0.0001")),
    ],
)
def test_rounds_to_4_places_half_even(raw: str, expected: Decimal) -> None:
    assert Dinheiro.de(raw).valor == expected


def test_multiply_by_quantity() -> None:
    assert Dinheiro.de("0.0345") * Decimal("1000") == Dinheiro.de("34.5")
    assert Dinheiro.de("2.50") * 3 == Dinheiro.de("7.50")


def test_multiply_rejects_float() -> None:
    with pytest.raises(InvalidValueError, match="float"):
        Dinheiro.de("2") * 1.5  # type: ignore[operator]


def test_sum_of_list() -> None:
    values = [Dinheiro.de("0.1")] * 10

    assert sum(values, Dinheiro.zero()) == Dinheiro.de("1")


def test_subtraction_and_negative() -> None:
    result = Dinheiro.de("1") - Dinheiro.de("3")

    assert result == Dinheiro.de("-2")
    assert result.is_negative
    assert not Dinheiro.zero().is_negative


def test_comparisons() -> None:
    assert Dinheiro.de("1.5") > Dinheiro.de("1.4999")
    assert Dinheiro.de("10") <= Dinheiro.de("10.0000")
    assert max(Dinheiro.de("3"), Dinheiro.de("7")) == Dinheiro.de("7")


def test_is_hashable_and_immutable() -> None:
    assert len({Dinheiro.de("1"), Dinheiro.de("1.0000")}) == 1

    with pytest.raises(AttributeError):
        Dinheiro.de("1").valor = Decimal("2")  # type: ignore[misc]
