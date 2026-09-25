"""Schemas das métricas (camada gold) e de /categorias.

Os read models de `ports/metricas.py` já têm os campos com os mesmos nomes, então
a conversão usa `from_attributes=True`: o Pydantic lê os atributos do dataclass,
inclusive os aninhados (a `Categoria` dentro do preço mensal).
"""

from datetime import date
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, Field

from radar.api.ids import para_id_publico
from radar.domain.enums import MaterialOuServico
from radar.ports.metricas import PrecoAcimaP90


class _FromAttributes(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CategoriaResponse(_FromAttributes):
    material_ou_servico: MaterialOuServico
    ncm_capitulo: str | None = Field(
        description="Valor para o filtro `categoria`; null = sem classificação (não filtrável)"
    )
    nome: str


class ValorMensalResponse(_FromAttributes):
    mes: date = Field(description="Primeiro dia do mês")
    contratacoes: int
    itens: int
    valor_total_estimado: Decimal
    media_movel_3m: Decimal
    meses_na_media: int = Field(description="Menor que 3 nos primeiros meses da série")


class PrecoCategoriaResponse(_FromAttributes):
    categoria: CategoriaResponse
    unidade: str
    mes: date
    itens: int
    preco_medio: Decimal
    preco_mediano: Decimal
    preco_mediano_mes_anterior: Decimal | None = Field(
        description="null quando o mês imediatamente anterior não teve itens"
    )
    variacao_percentual: Decimal | None


class RankingFornecedorResponse(_FromAttributes):
    orgao_cnpj: str
    orgao_razao_social: str
    fornecedor_documento: str
    fornecedor_nome: str
    itens_vencidos: int
    valor_total_homologado: Decimal
    ranking: int = Field(description="RANK: empatados dividem a posição e a seguinte é pulada")
    participacao_percentual: Decimal | None


class PrecoAcimaP90Response(BaseModel):
    contratacao_id: str = Field(description="Id público, para GET /contratacoes/{id}")
    numero_controle_pncp: str
    numero_item: int
    orgao_razao_social: str
    categoria_nome: str
    unidade: str
    data_publicacao: date
    valor_unitario_estimado: Decimal
    percentil_preco: Decimal = Field(description="0 = mais barato, 1 = mais caro do grupo")
    itens_comparaveis: int

    @classmethod
    def de(cls, item: PrecoAcimaP90) -> Self:
        return cls(
            contratacao_id=para_id_publico(item.numero_controle_pncp),
            numero_controle_pncp=item.numero_controle_pncp,
            numero_item=item.numero_item,
            orgao_razao_social=item.orgao_razao_social,
            categoria_nome=item.categoria_nome,
            unidade=item.unidade,
            data_publicacao=item.data_publicacao,
            valor_unitario_estimado=item.valor_unitario_estimado,
            percentil_preco=item.percentil_preco,
            itens_comparaveis=item.itens_comparaveis,
        )
