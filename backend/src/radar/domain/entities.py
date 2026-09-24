"""Entidades do domínio: os conceitos de negócio e suas regras.

Este módulo não importa nada de banco, HTTP ou framework: só a biblioteca padrão e
o próprio domínio. As regras rodam na criação (`__post_init__`), então uma entidade
que existe em memória é sempre válida.

As entidades são identificadas pela chave natural do negócio (CNPJ, número de
controle do PNCP). O `id` numérico do banco é detalhe do adapter e não aparece aqui.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from radar.domain.enums import (
    Esfera,
    MaterialOuServico,
    Modalidade,
    Poder,
    SituacaoContratacao,
    TipoPessoa,
)
from radar.domain.errors import BusinessRuleError, InvalidValueError
from radar.domain.value_objects import Cnpj, Cpf, Dinheiro, to_decimal

# as 27 unidades da federação (26 estados + DF)
UFS = frozenset(
    {"AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA"}
    | {"PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO"}
)

# CNPJ do órgão - 1 (tipo "contratação") - sequencial com 6 dígitos / ano
_NCM_NBS = re.compile(r"\d{2,9}")
_NUMERO_CONTROLE = re.compile(r"^(?P<cnpj>[0-9A-Z]{12}\d{2})-1-(?P<seq>\d{6})/(?P<ano>\d{4})$")


def _required_text(value: str, field_name: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise InvalidValueError(f"{field_name} não pode ser vazio")
    return stripped


def _non_negative(value: Dinheiro | None, field_name: str) -> None:
    if value is not None and value.is_negative:
        raise BusinessRuleError(f"{field_name} não pode ser negativo: {value.valor}")


@dataclass(slots=True, kw_only=True)
class Orgao:
    cnpj: Cnpj
    razao_social: str
    esfera: Esfera
    poder: Poder

    def __post_init__(self) -> None:
        self.razao_social = _required_text(self.razao_social, "razao_social")


@dataclass(slots=True, kw_only=True)
class Fornecedor:
    """Quem vende para o governo. O documento depende do tipo de pessoa."""

    tipo_pessoa: TipoPessoa
    documento: str
    nome: str

    def __post_init__(self) -> None:
        self.nome = _required_text(self.nome, "nome")
        match self.tipo_pessoa:
            case TipoPessoa.JURIDICA:
                self.documento = Cnpj(self.documento).value
            case TipoPessoa.FISICA:
                self.documento = Cpf(self.documento).value
            case TipoPessoa.ESTRANGEIRA:
                # estrangeira usa o identificador do país de origem: sem validação de formato
                self.documento = _required_text(self.documento, "documento")


@dataclass(frozen=True, slots=True, kw_only=True)
class ItemContratacao:
    """Um item da contratação. O resultado (fornecedor + preço homologado) é opcional.

    `valor_unitario_estimado` é `None` quando o orçamento é sigiloso: o valor existe,
    mas não é público. Nunca usar 0 para isso (0 envenenaria médias e o sobrepreço).
    """

    numero_item: int
    descricao: str
    material_ou_servico: MaterialOuServico
    categoria: str | None
    quantidade: Decimal
    unidade_medida: str
    valor_unitario_estimado: Dinheiro | None
    fornecedor_documento: str | None = None
    valor_unitario_homologado: Dinheiro | None = None
    # classificação: NCM (mercadoria) ou NBS (serviço), só dígitos; base da categoria no dbt
    ncm_nbs: str | None = None

    def __post_init__(self) -> None:
        if self.numero_item < 1:
            raise BusinessRuleError(f"numero_item deve ser >= 1: {self.numero_item}")
        if self.ncm_nbs is not None and not _NCM_NBS.fullmatch(self.ncm_nbs):
            raise InvalidValueError(f"código NCM/NBS inválido: {self.ncm_nbs!r}")
        object.__setattr__(self, "descricao", _required_text(self.descricao, "descricao"))
        quantidade = to_decimal(self.quantidade, "quantidade")
        if quantidade <= 0:
            raise BusinessRuleError(f"quantidade deve ser positiva: {quantidade}")
        object.__setattr__(self, "quantidade", quantidade)
        _non_negative(self.valor_unitario_estimado, "valor_unitario_estimado")
        _non_negative(self.valor_unitario_homologado, "valor_unitario_homologado")
        if (self.fornecedor_documento is None) != (self.valor_unitario_homologado is None):
            raise BusinessRuleError(
                "fornecedor_documento e valor_unitario_homologado devem vir juntos "
                "(resultado do item)"
            )

    @property
    def valor_total_estimado(self) -> Dinheiro | None:
        """Calculado, nunca armazenado: não tem como ficar inconsistente."""
        if self.valor_unitario_estimado is None:
            return None
        return self.valor_unitario_estimado * self.quantidade

    @property
    def tem_resultado(self) -> bool:
        return self.fornecedor_documento is not None


@dataclass(slots=True, kw_only=True)
class Contratacao:
    """Contratação publicada no PNCP. É a raiz do agregado: os itens só mudam por ela."""

    numero_controle_pncp: str
    orgao_cnpj: Cnpj
    modalidade: Modalidade
    situacao: SituacaoContratacao
    objeto: str
    valor_total_estimado: Dinheiro | None
    data_publicacao: datetime
    uf: str
    municipio: str
    itens: Sequence[ItemContratacao] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not _NUMERO_CONTROLE.match(self.numero_controle_pncp):
            raise InvalidValueError(f"numero_controle_pncp inválido: {self.numero_controle_pncp!r}")
        self.objeto = _required_text(self.objeto, "objeto")
        self.municipio = _required_text(self.municipio, "municipio")
        _non_negative(self.valor_total_estimado, "valor_total_estimado")
        if self.data_publicacao.tzinfo is None:
            raise InvalidValueError("data_publicacao precisa ter fuso horário (datetime aware)")
        if self.uf not in UFS:
            raise InvalidValueError(f"UF inválida: {self.uf!r}")
        items = tuple(self.itens)
        self.itens = ()
        for item in items:
            self.add_item(item)

    @property
    def ano(self) -> int:
        return int(self._numero_controle_part("ano"))

    @property
    def sequencial(self) -> int:
        return int(self._numero_controle_part("seq"))

    def add_item(self, item: ItemContratacao) -> None:
        current = tuple(self.itens)
        if any(existing.numero_item == item.numero_item for existing in current):
            raise BusinessRuleError(f"numero_item duplicado na contratação: {item.numero_item}")
        # tupla: quem lê `itens` não consegue fazer append e pular esta validação
        self.itens = (*current, item)

    def valor_total_itens(self) -> Dinheiro | None:
        """Soma dos itens; desconhecida (`None`) se algum item tiver valor sigiloso."""
        total = Dinheiro.zero()
        for item in self.itens:
            valor = item.valor_total_estimado
            if valor is None:
                return None
            total += valor
        return total

    def _numero_controle_part(self, name: str) -> str:
        match = _NUMERO_CONTROLE.match(self.numero_controle_pncp)
        if match is None:  # impossível após o __post_init__; protege contra mutação externa
            raise InvalidValueError(f"numero_controle_pncp inválido: {self.numero_controle_pncp!r}")
        return match.group(name)
