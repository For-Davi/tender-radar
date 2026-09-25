"""Schemas de /orgaos."""

from typing import Self

from pydantic import BaseModel

from radar.api import rotulos
from radar.api.schemas.comum import PaginacaoParams, UfParam
from radar.domain.enums import Esfera, Poder
from radar.ports.consultas import OrgaoResumo


class OrgaosParams(PaginacaoParams):
    uf: UfParam | None = None


class OrgaoResponse(BaseModel):
    cnpj: str
    razao_social: str
    esfera: Esfera
    esfera_nome: str
    poder: Poder
    poder_nome: str
    total_contratacoes: int

    @classmethod
    def de(cls, orgao: OrgaoResumo) -> Self:
        return cls(
            cnpj=orgao.cnpj,
            razao_social=orgao.razao_social,
            esfera=orgao.esfera,
            esfera_nome=rotulos.ESFERA[orgao.esfera],
            poder=orgao.poder,
            poder_nome=rotulos.PODER[orgao.poder],
            total_contratacoes=orgao.total_contratacoes,
        )
