"""Regras de limpeza (normalização) do dado bruto: funções puras, sem I/O.

Cada função recebe um valor "como veio" (`object`: o bruto pode ter qualquer tipo) e
devolve o valor limpo, ou levanta `ValueError` com uma mensagem clara. Levantar
`ValueError` é o combinado com o Pydantic: dentro de um validator, ele vira um erro de
validação que aponta o campo (ver `schemas_bronze.py`).
"""

import unicodedata
from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

# o PNCP manda datas sem fuso, no horário de Brasília
BRASILIA = ZoneInfo("America/Sao_Paulo")

# valores que aparecem no lugar de "não tem categoria" (comparados sem acento/caixa)
_PLACEHOLDERS_CATEGORIA = frozenset({"nao se aplica", "-", "n/a"})


# ------------------------------------------------------------------ números


def para_decimal(valor: object) -> Decimal:
    """Converte número do bruto para Decimal exato.

    - float JSON: via `str` (representação mais curta), para manter o que a API enviou
      (`0.1` -> `Decimal("0.1")`, e não `0.1000000000000000055...`);
    - texto com vírgula: formato brasileiro (`"1.234,56"` -> `1234.56`);
    - texto sem vírgula: ponto decimal (`"1234.56"`), o padrão do JSON.
    """
    # bool antes de int: em Python, True é um int
    if isinstance(valor, bool) or valor is None:
        raise ValueError(f"não é um número: {valor!r}")
    if isinstance(valor, Decimal | int):
        resultado = Decimal(valor)
    elif isinstance(valor, float):
        resultado = _parse_decimal(str(valor), valor)
    elif isinstance(valor, str):
        resultado = _parse_decimal(_texto_numerico(valor), valor)
    else:
        raise ValueError(f"não é um número: {valor!r}")
    if not resultado.is_finite():
        raise ValueError(f"número não finito: {valor!r}")
    return resultado


def para_decimal_opcional(valor: object) -> Decimal | None:
    return None if valor is None else para_decimal(valor)


def _texto_numerico(valor: str) -> str:
    texto = valor.strip()
    if texto.count(",") > 1:
        raise ValueError(f"não é um número: {valor!r}")
    if "," in texto:
        # formato brasileiro: ponto separa milhar, vírgula separa decimais
        texto = texto.replace(".", "").replace(",", ".")
    return texto


def _parse_decimal(texto: str, original: object) -> Decimal:
    try:
        return Decimal(texto)
    except InvalidOperation as exc:
        raise ValueError(f"não é um número: {original!r}") from exc


# ------------------------------------------------------------------ datas


def para_datetime(valor: object) -> datetime:
    """Data/hora ISO 8601; sem fuso = horário de Brasília (o PNCP manda assim)."""
    if isinstance(valor, datetime):
        resultado = valor
    elif isinstance(valor, str):
        try:
            resultado = datetime.fromisoformat(valor.strip())
        except ValueError as exc:
            raise ValueError(f"data inválida: {valor!r}") from exc
    else:
        raise ValueError(f"data inválida: {valor!r}")
    if resultado.tzinfo is None:
        # replace (e não astimezone): o relógio já é de Brasília, só falta dizer isso
        resultado = resultado.replace(tzinfo=BRASILIA)
    return resultado


# ------------------------------------------------------------------ textos


def normalizar_texto(valor: object) -> str | None:
    """Tira espaços das pontas, junta espaços repetidos; texto vazio vira None."""
    if valor is None:
        return None
    if not isinstance(valor, str):
        raise ValueError(f"esperava texto: {valor!r}")
    # split() sem argumento quebra em qualquer espaço (inclusive \n e \t) e ignora vazios
    texto = " ".join(valor.split())
    return texto or None


def texto_obrigatorio(valor: object) -> str:
    texto = normalizar_texto(valor)
    if texto is None:
        raise ValueError("texto obrigatório está vazio")
    return texto


def normalizar_categoria(valor: object) -> str | None:
    texto = normalizar_texto(valor)
    if texto is None or _sem_acento(texto.casefold()) in _PLACEHOLDERS_CATEGORIA:
        return None
    return texto


def _sem_acento(texto: str) -> str:
    # NFKD separa a letra do acento ("ã" -> "a" + "~"); depois descartamos os acentos
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(char for char in decomposto if not unicodedata.combining(char))
