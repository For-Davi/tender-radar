"""Rota de /categorias: os valores possíveis do filtro `categoria` (dimensão da gold)."""

from fastapi import APIRouter

from radar.api.dependencies import MetricasQueriesDep
from radar.api.errors import problem_responses
from radar.api.schemas.metricas import CategoriaResponse

router = APIRouter(prefix="/categorias", tags=["categorias"])


@router.get("", responses=problem_responses(503))
def listar_categorias(queries: MetricasQueriesDep) -> list[CategoriaResponse]:
    """Categorias (tipo + capítulo NCM/NBS). Use `ncm_capitulo` no filtro `categoria`."""
    return [CategoriaResponse.model_validate(c) for c in queries.categorias()]
