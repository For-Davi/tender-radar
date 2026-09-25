"""Rotas de /metricas: leitura dos marts do dbt (camada gold, Etapa 04).

A gold só é atualizada quando o `make dbt` roda. Se ela ainda não existir, as rotas
respondem 503 (ver `api/errors.py`).
"""

from typing import Annotated

from fastapi import APIRouter, Query

from radar.api.dependencies import MetricasQueriesDep
from radar.api.errors import problem_responses
from radar.api.schemas.comum import CapituloParam, CnpjParam, PaginacaoParams, PaginaResponse
from radar.api.schemas.metricas import (
    PrecoAcimaP90Response,
    PrecoCategoriaResponse,
    RankingFornecedorResponse,
    ValorMensalResponse,
)

router = APIRouter(prefix="/metricas", tags=["métricas"], responses=problem_responses(503))


@router.get("/valor-mensal")
def valor_mensal(queries: MetricasQueriesDep) -> list[ValorMensalResponse]:
    """Valor estimado contratado por mês, com média móvel de 3 meses (sem buracos)."""
    return [ValorMensalResponse.model_validate(v) for v in queries.valor_mensal()]


@router.get("/preco-categoria", responses=problem_responses(422))
def preco_categoria(
    queries: MetricasQueriesDep, categoria: Annotated[CapituloParam | None, Query()] = None
) -> list[PrecoCategoriaResponse]:
    """Preço mediano por categoria, unidade e mês, com a variação sobre o mês anterior."""
    return [PrecoCategoriaResponse.model_validate(p) for p in queries.preco_categoria(categoria)]


@router.get("/ranking-fornecedores", responses=problem_responses(422))
def ranking_fornecedores(
    queries: MetricasQueriesDep, orgao: Annotated[CnpjParam | None, Query()] = None
) -> list[RankingFornecedorResponse]:
    """Ranking dos fornecedores de cada órgão pelo valor homologado."""
    return [
        RankingFornecedorResponse.model_validate(r) for r in queries.ranking_fornecedores(orgao)
    ]


@router.get("/precos-acima-p90", responses=problem_responses(422))
def precos_acima_p90(
    params: Annotated[PaginacaoParams, Query()], queries: MetricasQueriesDep
) -> PaginaResponse[PrecoAcimaP90Response]:
    """Itens com preço no percentil 90 ou acima entre os comparáveis (base do sobrepreço).

    Só entram itens de categoria classificada (com NCM) e grupos com amostra mínima.
    """
    pagina = queries.precos_acima_p90(params.pedido())
    return PaginaResponse[PrecoAcimaP90Response].de(
        pagina, [PrecoAcimaP90Response.de(item) for item in pagina.itens]
    )
