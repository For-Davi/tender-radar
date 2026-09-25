"""Rotas de /contratacoes (lidas da silver: sempre atualizadas)."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query

from radar.api.dependencies import ContratacaoQueriesDep
from radar.api.errors import problem_responses
from radar.api.ids import ID_PUBLICO_PATTERN, para_numero_controle
from radar.api.schemas.comum import PaginaResponse
from radar.api.schemas.contratacoes import (
    ContratacaoDetalheResponse,
    ContratacaoResponse,
    ContratacoesParams,
)

router = APIRouter(prefix="/contratacoes", tags=["contratações"])


@router.get("", responses=problem_responses(422))
def listar_contratacoes(
    params: Annotated[ContratacoesParams, Query()], queries: ContratacaoQueriesDep
) -> PaginaResponse[ContratacaoResponse]:
    """Lista contratações com filtros combináveis, paginação e ordenação."""
    pagina = queries.listar(params.filtro(), params.ordenar, params.pedido())
    return PaginaResponse[ContratacaoResponse].de(
        pagina, [ContratacaoResponse.de(resumo) for resumo in pagina.itens]
    )


@router.get("/{id}", responses=problem_responses(404, 422))
def detalhar_contratacao(
    id: Annotated[
        str,
        Path(
            pattern=ID_PUBLICO_PATTERN,
            description="Número de controle PNCP com '-' no lugar de '/'",
            examples=["07954480000179-1-000123-2025"],
        ),
    ],
    queries: ContratacaoQueriesDep,
) -> ContratacaoDetalheResponse:
    """Detalhe de uma contratação, com o órgão e todos os itens (e o vencedor de cada um)."""
    # o Path(pattern=...) já garantiu o formato: um id malformado nem chega aqui (422)
    detalhe = queries.detalhar(para_numero_controle(id))
    if detalhe is None:
        raise HTTPException(404, f"contratação não encontrada: {id}")
    return ContratacaoDetalheResponse.de_detalhe(detalhe)
