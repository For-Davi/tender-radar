"""Rotas de /orgaos (lidas da silver)."""

from typing import Annotated

from fastapi import APIRouter, Query

from radar.api.dependencies import OrgaoQueriesDep
from radar.api.errors import problem_responses
from radar.api.schemas.comum import PaginaResponse
from radar.api.schemas.orgaos import OrgaoResponse, OrgaosParams

router = APIRouter(prefix="/orgaos", tags=["órgãos"])


@router.get("", responses=problem_responses(422))
def listar_orgaos(
    params: Annotated[OrgaosParams, Query()], queries: OrgaoQueriesDep
) -> PaginaResponse[OrgaoResponse]:
    """Órgãos em ordem alfabética. Com `uf`, só os que publicaram contratações na UF."""
    pagina = queries.listar(params.uf, params.pedido())
    return PaginaResponse[OrgaoResponse].de(
        pagina, [OrgaoResponse.de(orgao) for orgao in pagina.itens]
    )
