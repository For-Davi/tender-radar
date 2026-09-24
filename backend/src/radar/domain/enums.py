"""Domínios fixos do PNCP.

Os valores numéricos e as siglas são os códigos usados pela API do PNCP (Manual de
Integração, tabelas de domínio). Guardar o próprio código facilita converter os
dados que chegam da API. A lista de modalidades será conferida com dados reais na
Etapa 02.
"""

from enum import IntEnum, StrEnum


class Modalidade(IntEnum):
    """Modalidade de contratação (`modalidadeId` no PNCP)."""

    LEILAO_ELETRONICO = 1
    DIALOGO_COMPETITIVO = 2
    CONCURSO = 3
    CONCORRENCIA_ELETRONICA = 4
    CONCORRENCIA_PRESENCIAL = 5
    PREGAO_ELETRONICO = 6
    PREGAO_PRESENCIAL = 7
    DISPENSA_DE_LICITACAO = 8
    INEXIGIBILIDADE = 9
    MANIFESTACAO_DE_INTERESSE = 10
    PRE_QUALIFICACAO = 11
    CREDENCIAMENTO = 12
    LEILAO_PRESENCIAL = 13


class SituacaoContratacao(IntEnum):
    """Situação da contratação (`situacaoCompraId` no PNCP)."""

    DIVULGADA = 1
    REVOGADA = 2
    ANULADA = 3
    SUSPENSA = 4


class TipoPessoa(StrEnum):
    JURIDICA = "PJ"
    FISICA = "PF"
    ESTRANGEIRA = "PE"


class Esfera(StrEnum):
    FEDERAL = "F"
    ESTADUAL = "E"
    MUNICIPAL = "M"
    DISTRITAL = "D"


class Poder(StrEnum):
    EXECUTIVO = "E"
    LEGISLATIVO = "L"
    JUDICIARIO = "J"
    NAO_SE_APLICA = "N"


class MaterialOuServico(StrEnum):
    MATERIAL = "M"
    SERVICO = "S"
