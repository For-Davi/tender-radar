"""Schemas de /contratacoes: parâmetros de filtro e o JSON de resposta."""

from datetime import date, datetime
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, Field, model_validator

from radar.api import rotulos
from radar.api.ids import para_id_publico
from radar.api.schemas.comum import CapituloParam, CnpjParam, PaginacaoParams, UfParam
from radar.domain.enums import MaterialOuServico, TipoPessoa
from radar.ports.consultas import (
    ContratacaoDetalhe,
    ContratacaoResumo,
    FiltroContratacoes,
    FornecedorRef,
    ItemDetalhe,
    Ordenacao,
)

# ------------------------------------------------------------------ entrada


class ContratacoesParams(PaginacaoParams):
    """Query string de GET /contratacoes. Todos os filtros são opcionais e combináveis."""

    uf: UfParam | None = None
    orgao: CnpjParam | None = None
    categoria: CapituloParam | None = None
    data_inicio: date | None = Field(None, description="Publicadas a partir deste dia")
    data_fim: date | None = Field(None, description="Publicadas até este dia (inclusive)")
    valor_min: Decimal | None = Field(None, ge=0, description="Valor total estimado mínimo")
    valor_max: Decimal | None = Field(None, ge=0, description="Valor total estimado máximo")
    ordenar: Ordenacao = Field(Ordenacao.DATA_DESC, description="`-` na frente = decrescente")

    @model_validator(mode="after")
    def _intervalos_coerentes(self) -> Self:
        # regras que envolvem DOIS campos: o validador de cada campo não enxerga o outro
        if self.data_inicio and self.data_fim and self.data_inicio > self.data_fim:
            raise ValueError("data_inicio não pode ser depois de data_fim")
        if (
            self.valor_min is not None
            and self.valor_max is not None
            and self.valor_min > self.valor_max
        ):
            raise ValueError("valor_min não pode ser maior que valor_max")
        return self

    def filtro(self) -> FiltroContratacoes:
        return FiltroContratacoes(
            uf=self.uf,
            orgao_cnpj=self.orgao,
            categoria=self.categoria,
            data_inicio=self.data_inicio,
            data_fim=self.data_fim,
            valor_min=self.valor_min,
            valor_max=self.valor_max,
        )


# ------------------------------------------------------------------ saída


class OrgaoRefResponse(BaseModel):
    cnpj: str
    razao_social: str


class ContratacaoResponse(BaseModel):
    id: str = Field(description="Id público: número de controle PNCP com '-' no lugar de '/'")
    numero_controle_pncp: str
    orgao: OrgaoRefResponse
    modalidade: int
    modalidade_nome: str
    situacao: int
    situacao_nome: str
    objeto: str
    valor_total_estimado: Decimal | None = Field(description="null = orçamento sigiloso")
    data_publicacao: datetime
    uf: str
    municipio: str
    total_itens: int

    @classmethod
    def de(cls, resumo: ContratacaoResumo) -> Self:
        return cls(
            id=para_id_publico(resumo.numero_controle_pncp),
            numero_controle_pncp=resumo.numero_controle_pncp,
            orgao=OrgaoRefResponse(cnpj=resumo.orgao.cnpj, razao_social=resumo.orgao.razao_social),
            modalidade=resumo.modalidade,
            modalidade_nome=rotulos.MODALIDADE[resumo.modalidade],
            situacao=resumo.situacao,
            situacao_nome=rotulos.SITUACAO[resumo.situacao],
            objeto=resumo.objeto,
            valor_total_estimado=resumo.valor_total_estimado,
            data_publicacao=resumo.data_publicacao,
            uf=resumo.uf,
            municipio=resumo.municipio,
            total_itens=resumo.total_itens,
        )


class FornecedorResponse(BaseModel):
    documento: str
    nome: str
    tipo_pessoa: TipoPessoa
    tipo_pessoa_nome: str

    @classmethod
    def de(cls, fornecedor: FornecedorRef) -> Self:
        return cls(
            documento=fornecedor.documento,
            nome=fornecedor.nome,
            tipo_pessoa=fornecedor.tipo_pessoa,
            tipo_pessoa_nome=rotulos.TIPO_PESSOA[fornecedor.tipo_pessoa],
        )


class ItemResponse(BaseModel):
    numero_item: int
    descricao: str
    material_ou_servico: MaterialOuServico
    material_ou_servico_nome: str
    ncm_nbs: str | None
    quantidade: Decimal
    unidade_medida: str
    valor_unitario_estimado: Decimal | None = Field(description="null = orçamento sigiloso")
    valor_total_estimado: Decimal | None
    vencedor: FornecedorResponse | None = Field(description="null = ainda sem resultado")
    valor_unitario_homologado: Decimal | None

    @classmethod
    def de(cls, item: ItemDetalhe) -> Self:
        return cls(
            numero_item=item.numero_item,
            descricao=item.descricao,
            material_ou_servico=item.material_ou_servico,
            material_ou_servico_nome=rotulos.MATERIAL_OU_SERVICO[item.material_ou_servico],
            ncm_nbs=item.ncm_nbs,
            quantidade=item.quantidade,
            unidade_medida=item.unidade_medida,
            valor_unitario_estimado=item.valor_unitario_estimado,
            valor_total_estimado=item.valor_total_estimado,
            vencedor=None if item.vencedor is None else FornecedorResponse.de(item.vencedor),
            valor_unitario_homologado=item.valor_unitario_homologado,
        )


class ContratacaoDetalheResponse(ContratacaoResponse):
    itens: list[ItemResponse]

    @classmethod
    def de_detalhe(cls, detalhe: ContratacaoDetalhe) -> Self:
        resumo = ContratacaoResponse.de(detalhe.resumo)
        return cls(**resumo.model_dump(), itens=[ItemResponse.de(item) for item in detalhe.itens])
