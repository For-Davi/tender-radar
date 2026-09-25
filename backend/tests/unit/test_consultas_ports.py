"""Testes dos tipos de apoio das consultas: paginação e item calculado."""

from decimal import Decimal

import pytest

from radar.domain.enums import MaterialOuServico
from radar.ports.consultas import ItemDetalhe, Pagina, PaginaPedido


def test_pedido_default_is_first_page_of_20() -> None:
    pedido = PaginaPedido()

    assert (pedido.pagina, pedido.tamanho, pedido.offset) == (1, 20, 0)


@pytest.mark.parametrize(
    ("pagina", "tamanho", "offset"),
    [(1, 10, 0), (2, 10, 10), (3, 20, 40), (5, 100, 400)],
)
def test_pedido_offset(pagina: int, tamanho: int, offset: int) -> None:
    assert PaginaPedido(pagina, tamanho).offset == offset


@pytest.mark.parametrize(("pagina", "tamanho"), [(0, 10), (-1, 10), (1, 0), (1, 101)])
def test_pedido_rejects_out_of_range(pagina: int, tamanho: int) -> None:
    with pytest.raises(ValueError, match=r"pagina|tamanho"):
        PaginaPedido(pagina, tamanho)


@pytest.mark.parametrize(
    ("total", "tamanho", "paginas"),
    [(0, 20, 0), (1, 20, 1), (20, 20, 1), (21, 20, 2), (41, 20, 3), (100, 100, 1)],
)
def test_total_paginas_rounds_up(total: int, tamanho: int, paginas: int) -> None:
    pagina: Pagina[str] = Pagina([], total, PaginaPedido(1, tamanho))

    assert pagina.total_paginas == paginas


def _item(valor: Decimal | None) -> ItemDetalhe:
    return ItemDetalhe(
        numero_item=1,
        descricao="Caneta",
        material_ou_servico=MaterialOuServico.MATERIAL,
        ncm_nbs=None,
        quantidade=Decimal("2.5"),
        unidade_medida="UN",
        valor_unitario_estimado=valor,
        vencedor=None,
        valor_unitario_homologado=None,
    )


def test_item_total_is_quantity_times_unit_price() -> None:
    assert _item(Decimal("0.10")).valor_total_estimado == Decimal("0.250")


def test_item_total_is_unknown_when_price_is_secret() -> None:
    assert _item(None).valor_total_estimado is None
