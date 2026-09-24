"""Rota de health check: responde se o processo da API está vivo."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["infra"])


class HealthResponse(BaseModel):
    status: Literal["ok"]


@router.get("/health")
def health() -> HealthResponse:
    """Usado pelo healthcheck do Docker e por monitores externos."""
    return HealthResponse(status="ok")
