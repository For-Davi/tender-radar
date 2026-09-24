"""Conversão entre entidades do domínio e linhas/modelos do banco.

- `*_values`: entidade -> dicionário de colunas (usado nos INSERT/UPSERT).
- `*_to_domain`: modelo carregado do banco -> entidade (as regras rodam de novo:
  um dado corrompido no banco vira erro, e não uma entidade inválida em memória).
"""

from decimal import Decimal

from radar.adapters.postgres.models import (
    ContratacaoModel,
    FornecedorModel,
    ItemContratacaoModel,
    OrgaoModel,
)
from radar.domain.entities import Contratacao, Fornecedor, ItemContratacao, Orgao
from radar.domain.enums import (
    Esfera,
    MaterialOuServico,
    Modalidade,
    Poder,
    SituacaoContratacao,
    TipoPessoa,
)
from radar.domain.value_objects import Cnpj, Dinheiro

Row = dict[str, object]


def _money_or_none(value: Dinheiro | None) -> Decimal | None:
    return None if value is None else value.valor


def _dinheiro_or_none(value: Decimal | None) -> Dinheiro | None:
    return None if value is None else Dinheiro(value)


# ------------------------------------------------------------------ Orgao


def orgao_values(orgao: Orgao) -> Row:
    return {
        "cnpj": orgao.cnpj.value,
        "razao_social": orgao.razao_social,
        "esfera": orgao.esfera.value,
        "poder": orgao.poder.value,
    }


def orgao_to_domain(model: OrgaoModel) -> Orgao:
    return Orgao(
        cnpj=Cnpj(model.cnpj),
        razao_social=model.razao_social,
        esfera=Esfera(model.esfera),
        poder=Poder(model.poder),
    )


# ------------------------------------------------------------------ Fornecedor


def fornecedor_values(fornecedor: Fornecedor) -> Row:
    return {
        "documento": fornecedor.documento,
        "tipo_pessoa": fornecedor.tipo_pessoa.value,
        "nome": fornecedor.nome,
    }


def fornecedor_to_domain(model: FornecedorModel) -> Fornecedor:
    return Fornecedor(
        tipo_pessoa=TipoPessoa(model.tipo_pessoa), documento=model.documento, nome=model.nome
    )


# ------------------------------------------------------------------ Contratacao


def contratacao_values(contratacao: Contratacao, orgao_id: int) -> Row:
    return {
        "numero_controle_pncp": contratacao.numero_controle_pncp,
        "orgao_id": orgao_id,
        "ano": contratacao.ano,
        "sequencial": contratacao.sequencial,
        "modalidade": contratacao.modalidade.value,
        "situacao": contratacao.situacao.value,
        "objeto": contratacao.objeto,
        "valor_total_estimado": _money_or_none(contratacao.valor_total_estimado),
        "data_publicacao": contratacao.data_publicacao,
        "uf": contratacao.uf,
        "municipio": contratacao.municipio,
    }


def item_values(item: ItemContratacao, contratacao_id: int, fornecedor_id: int | None) -> Row:
    return {
        "contratacao_id": contratacao_id,
        "numero_item": item.numero_item,
        "descricao": item.descricao,
        "material_ou_servico": item.material_ou_servico.value,
        "categoria": item.categoria,
        "quantidade": item.quantidade,
        "unidade_medida": item.unidade_medida,
        "valor_unitario_estimado": _money_or_none(item.valor_unitario_estimado),
        "fornecedor_id": fornecedor_id,
        "valor_unitario_homologado": _money_or_none(item.valor_unitario_homologado),
        "ncm_nbs": item.ncm_nbs,
    }


def item_to_domain(model: ItemContratacaoModel) -> ItemContratacao:
    return ItemContratacao(
        numero_item=model.numero_item,
        descricao=model.descricao,
        material_ou_servico=MaterialOuServico(model.material_ou_servico),
        categoria=model.categoria,
        quantidade=model.quantidade,
        unidade_medida=model.unidade_medida,
        valor_unitario_estimado=_dinheiro_or_none(model.valor_unitario_estimado),
        fornecedor_documento=model.fornecedor.documento if model.fornecedor else None,
        valor_unitario_homologado=_dinheiro_or_none(model.valor_unitario_homologado),
        ncm_nbs=model.ncm_nbs,
    )


def contratacao_to_domain(model: ContratacaoModel) -> Contratacao:
    """Espera `orgao`, `itens` e `itens.fornecedor` já carregados (relacionamentos lazy=raise)."""
    return Contratacao(
        numero_controle_pncp=model.numero_controle_pncp,
        orgao_cnpj=Cnpj(model.orgao.cnpj),
        modalidade=Modalidade(model.modalidade),
        situacao=SituacaoContratacao(model.situacao),
        objeto=model.objeto,
        valor_total_estimado=_dinheiro_or_none(model.valor_total_estimado),
        data_publicacao=model.data_publicacao,
        uf=model.uf,
        municipio=model.municipio,
        itens=[item_to_domain(item) for item in model.itens],
    )
