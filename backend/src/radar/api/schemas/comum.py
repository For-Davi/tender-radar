"""Tipos compartilhados pelos schemas: paginação e parâmetros validados na borda."""

from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, Field

from radar.domain.entities import UFS
from radar.domain.value_objects import Cnpj
from radar.ports.consultas import TAMANHO_PAGINA_MAXIMO, Pagina, PaginaPedido


def _uf(value: str) -> str:
    uf = value.strip().upper()
    if uf not in UFS:
        raise ValueError(f"UF inválida: {value!r}")
    return uf


def _cnpj(value: str) -> str:
    # o InvalidValueError do domínio é um ValueError: o Pydantic o transforma em 422
    return Cnpj(value).value


# Annotated junta tipo + validação + documentação num nome reutilizável
UfParam = Annotated[str, AfterValidator(_uf), Field(description="Sigla da UF, ex.: CE")]
CnpjParam = Annotated[
    str,
    AfterValidator(_cnpj),
    Field(description="CNPJ do órgão, com ou sem máscara", examples=["07.954.480/0001-79"]),
]
CapituloParam = Annotated[
    str,
    Field(
        pattern=r"^\d{2}$",
        description="Capítulo NCM/NBS (2 dígitos). Valores em GET /categorias",
        examples=["30"],
    ),
]


class PaginacaoParams(BaseModel):
    pagina: int = Field(1, ge=1, description="Página desejada (1 = primeira)")
    tamanho_pagina: int = Field(20, ge=1, le=TAMANHO_PAGINA_MAXIMO, description="Itens por página")

    def pedido(self) -> PaginaPedido:
        return PaginaPedido(self.pagina, self.tamanho_pagina)


class PaginaResponse[T](BaseModel):
    """Envelope das listas paginadas. Página além da última = `itens` vazio (200)."""

    itens: list[T]
    total: int = Field(description="Registros que atendem ao filtro, em todas as páginas")
    pagina: int
    tamanho_pagina: int
    total_paginas: int

    @classmethod
    def de(cls, pagina: Pagina[Any], itens: list[T]) -> "PaginaResponse[T]":
        return cls(
            itens=itens,
            total=pagina.total,
            pagina=pagina.pedido.pagina,
            tamanho_pagina=pagina.pedido.tamanho,
            total_paginas=pagina.total_paginas,
        )
