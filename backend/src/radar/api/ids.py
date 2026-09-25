"""Identificador público de uma contratação na API.

A chave natural é o número de controle do PNCP: `13183513000127-1-000173/2025`.
A barra quebra URLs (`/contratacoes/13183513000127-1-000173/2025` pareceria
duas partes do caminho), então a API troca a `/` por `-`:
`13183513000127-1-000173-2025`.

Por que não o `id` numérico da silver? Ele é detalhe do banco (ADR 0002) e muda se o
banco for recriado; um link salvo no frontend quebraria. O número de controle é
estável e é o mesmo que o próprio PNCP mostra.
"""

import re

from radar.domain.errors import InvalidValueError

# CNPJ (12 alfanuméricos + 2 dígitos) - 1 - sequencial (6) - ano (4)
ID_PUBLICO_PATTERN = r"^[0-9A-Z]{12}\d{2}-1-\d{6}-\d{4}$"
_ID_PUBLICO = re.compile(ID_PUBLICO_PATTERN)


def para_id_publico(numero_controle_pncp: str) -> str:
    """`...-000173/2025` -> `...-000173-2025`."""
    return numero_controle_pncp.replace("/", "-")


def para_numero_controle(id_publico: str) -> str:
    """`...-000173-2025` -> `...-000173/2025`. Levanta erro se o formato for inválido."""
    if not _ID_PUBLICO.match(id_publico):
        raise InvalidValueError(f"id de contratação inválido: {id_publico!r}")
    # o ano são sempre os 4 últimos caracteres, precedidos do "-" que era a "/"
    return f"{id_publico[:-5]}/{id_publico[-4:]}"
