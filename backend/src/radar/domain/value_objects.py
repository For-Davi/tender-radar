"""Value objects: valores imutáveis, definidos pelo conteúdo e sempre válidos.

Se um `Cnpj` existe, ele é válido: a validação acontece na criação. Dois value
objects com o mesmo conteúdo são iguais (`Cnpj("11.222...") == Cnpj("11222...")`).
"""

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Self

from radar.domain.errors import InvalidValueError

# ------------------------------------------------------------------ documentos

_MASK_CHARS = re.compile(r"[.\-/\s]")
# CNPJ alfanumérico (IN RFB 2.229/2024): 12 posições 0-9/A-Z + 2 dígitos verificadores numéricos
_CNPJ_FORMAT = re.compile(r"^[0-9A-Z]{12}[0-9]{2}$")
_CPF_FORMAT = re.compile(r"^[0-9]{11}$")
_CNPJ_WEIGHTS = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)


def _strip_mask(raw: str) -> str:
    return _MASK_CHARS.sub("", raw).upper()


def _cnpj_check_digit(base: str) -> str:
    # o valor de cada caractere é o código ASCII menos 48: '0'..'9' -> 0..9, 'A' -> 17...
    weights = _CNPJ_WEIGHTS if len(base) == 12 else (6, *_CNPJ_WEIGHTS)
    remainder = sum((ord(char) - 48) * w for char, w in zip(base, weights, strict=True)) % 11
    return "0" if remainder < 2 else str(11 - remainder)


def _is_valid_cnpj(value: str) -> bool:
    if not _CNPJ_FORMAT.match(value) or len(set(value)) == 1:
        return False
    first = _cnpj_check_digit(value[:12])
    second = _cnpj_check_digit(value[:12] + first)
    return value[12:] == first + second


def _cpf_check_digit(base: str) -> str:
    start_weight = len(base) + 1  # 10 para o 1º dígito, 11 para o 2º
    total = sum(int(d) * w for d, w in zip(base, range(start_weight, 1, -1), strict=True))
    return str(total * 10 % 11 % 10)


def _is_valid_cpf(value: str) -> bool:
    if not _CPF_FORMAT.match(value) or len(set(value)) == 1:
        return False
    first = _cpf_check_digit(value[:9])
    return value[9:] == first + _cpf_check_digit(value[:9] + first)


@dataclass(frozen=True, slots=True)
class Cnpj:
    """CNPJ normalizado (sem máscara, maiúsculo), numérico ou alfanumérico."""

    value: str

    def __post_init__(self) -> None:
        normalized = _strip_mask(self.value)
        if not _is_valid_cnpj(normalized):
            raise InvalidValueError(f"CNPJ inválido: {self.value!r}")
        # frozen=True bloqueia atribuição; object.__setattr__ é o jeito oficial de
        # ajustar o valor dentro do próprio __post_init__
        object.__setattr__(self, "value", normalized)

    def formatted(self) -> str:
        v = self.value
        return f"{v[:2]}.{v[2:5]}.{v[5:8]}/{v[8:12]}-{v[12:]}"


@dataclass(frozen=True, slots=True)
class Cpf:
    """CPF normalizado (só dígitos)."""

    value: str

    def __post_init__(self) -> None:
        normalized = _strip_mask(self.value)
        if not _is_valid_cpf(normalized):
            raise InvalidValueError(f"CPF inválido: {self.value!r}")
        object.__setattr__(self, "value", normalized)

    def formatted(self) -> str:
        v = self.value
        return f"{v[:3]}.{v[3:6]}.{v[6:9]}-{v[9:]}"


# ------------------------------------------------------------------ dinheiro

_FOUR_PLACES = Decimal("0.0001")


def to_decimal(raw: Decimal | int | str, field: str) -> Decimal:
    """Converte para Decimal recusando float e bool, e valores não finitos (NaN, Infinity)."""
    # bool vem antes de int: em Python, True é um int (True == 1)
    if isinstance(raw, float | bool):
        raise InvalidValueError(f"{field}: use str, int ou Decimal, nunca float/bool ({raw!r})")
    try:
        value = raw if isinstance(raw, Decimal) else Decimal(str(raw).strip())
    except InvalidOperation as exc:
        raise InvalidValueError(f"{field}: valor numérico inválido {raw!r}") from exc
    if not value.is_finite():
        raise InvalidValueError(f"{field}: valor não finito {raw!r}")
    return value


@dataclass(frozen=True, slots=True, order=True)
class Dinheiro:
    """Valor monetário em reais, exato (Decimal) com 4 casas decimais.

    4 casas (e não 2) porque preços unitários do PNCP podem ter frações de centavo
    (ex.: R$ 0,0345 por unidade). O arredondamento é "meio para o par"
    (ROUND_HALF_EVEN, o da ABNT NBR 5891), que não enviesa somas grandes para cima.
    """

    valor: Decimal

    def __post_init__(self) -> None:
        exact = to_decimal(self.valor, "Dinheiro")
        object.__setattr__(self, "valor", exact.quantize(_FOUR_PLACES, rounding=ROUND_HALF_EVEN))

    @classmethod
    def de(cls, raw: Decimal | int | str) -> Self:
        """Cria a partir de str, int ou Decimal (float é recusado)."""
        return cls(to_decimal(raw, "Dinheiro"))

    @classmethod
    def zero(cls) -> Self:
        return cls(Decimal(0))

    @property
    def is_negative(self) -> bool:
        return self.valor < 0

    def __add__(self, other: Self) -> Self:
        return type(self)(self.valor + other.valor)

    def __sub__(self, other: Self) -> Self:
        return type(self)(self.valor - other.valor)

    def __mul__(self, factor: Decimal | int) -> Self:
        return type(self)(self.valor * to_decimal(factor, "multiplicador"))
