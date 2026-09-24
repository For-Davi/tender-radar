"""Fábricas de objetos de domínio válidos para os testes.

Cada teste muda só o campo que interessa (`make_item(quantidade=0)`) e o resto
vem preenchido com valores válidos. Assim o teste mostra exatamente o que está
sendo verificado.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

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

CNPJ_ORGAO = "11222333000181"
CNPJ_FORNECEDOR = "12ABC34501DE35"

# Any: os overrides são repassados como kwargs e cada entidade valida seus próprios tipos


def make_orgao(**overrides: Any) -> Orgao:
    fields: dict[str, Any] = {
        "cnpj": Cnpj(CNPJ_ORGAO),
        "razao_social": "Prefeitura Municipal de Exemplo",
        "esfera": Esfera.MUNICIPAL,
        "poder": Poder.EXECUTIVO,
    }
    return Orgao(**(fields | overrides))


def make_fornecedor(**overrides: Any) -> Fornecedor:
    fields: dict[str, Any] = {
        "tipo_pessoa": TipoPessoa.JURIDICA,
        "documento": CNPJ_FORNECEDOR,
        "nome": "Fornecedor Exemplo Ltda",
    }
    return Fornecedor(**(fields | overrides))


def make_item(**overrides: Any) -> ItemContratacao:
    fields: dict[str, Any] = {
        "numero_item": 1,
        "descricao": "Notebook 16GB",
        "material_ou_servico": MaterialOuServico.MATERIAL,
        "categoria": "Informática",
        "quantidade": Decimal("10"),
        "unidade_medida": "UN",
        "valor_unitario_estimado": Dinheiro.de("4999.90"),
    }
    return ItemContratacao(**(fields | overrides))


def make_contratacao(**overrides: Any) -> Contratacao:
    fields: dict[str, Any] = {
        "numero_controle_pncp": f"{CNPJ_ORGAO}-1-000123/2025",
        "orgao_cnpj": Cnpj(CNPJ_ORGAO),
        "modalidade": Modalidade.PREGAO_ELETRONICO,
        "situacao": SituacaoContratacao.DIVULGADA,
        "objeto": "Aquisição de notebooks para a rede municipal de ensino",
        "valor_total_estimado": Dinheiro.de("49999.00"),
        "data_publicacao": datetime(2025, 3, 10, 12, 0, tzinfo=UTC),
        "uf": "CE",
        "municipio": "Fortaleza",
        "itens": [make_item()],
    }
    return Contratacao(**(fields | overrides))
