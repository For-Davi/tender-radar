"""Nomes legíveis dos códigos do PNCP, para a API devolver junto com o código.

É apresentação, e por isso fica na API, e não no domínio. Os nomes são os mesmos do
dbt (`stg_contratacao`, `stg_orgao`), para o dashboard mostrar o mesmo texto venha o
dado da silver ou da gold. Um teste garante que todo membro de cada enum tem nome.
"""

from radar.domain.enums import (
    Esfera,
    MaterialOuServico,
    Modalidade,
    Poder,
    SituacaoContratacao,
    TipoPessoa,
)

MODALIDADE = {
    Modalidade.LEILAO_ELETRONICO: "Leilão eletrônico",
    Modalidade.DIALOGO_COMPETITIVO: "Diálogo competitivo",
    Modalidade.CONCURSO: "Concurso",
    Modalidade.CONCORRENCIA_ELETRONICA: "Concorrência eletrônica",
    Modalidade.CONCORRENCIA_PRESENCIAL: "Concorrência presencial",
    Modalidade.PREGAO_ELETRONICO: "Pregão eletrônico",
    Modalidade.PREGAO_PRESENCIAL: "Pregão presencial",
    Modalidade.DISPENSA_DE_LICITACAO: "Dispensa de licitação",
    Modalidade.INEXIGIBILIDADE: "Inexigibilidade",
    Modalidade.MANIFESTACAO_DE_INTERESSE: "Manifestação de interesse",
    Modalidade.PRE_QUALIFICACAO: "Pré-qualificação",
    Modalidade.CREDENCIAMENTO: "Credenciamento",
    Modalidade.LEILAO_PRESENCIAL: "Leilão presencial",
}

SITUACAO = {
    SituacaoContratacao.DIVULGADA: "Divulgada no PNCP",
    SituacaoContratacao.REVOGADA: "Revogada",
    SituacaoContratacao.ANULADA: "Anulada",
    SituacaoContratacao.SUSPENSA: "Suspensa",
}

ESFERA = {
    Esfera.FEDERAL: "Federal",
    Esfera.ESTADUAL: "Estadual",
    Esfera.MUNICIPAL: "Municipal",
    Esfera.DISTRITAL: "Distrital",
    Esfera.NAO_SE_APLICA: "Não se aplica",
}

PODER = {
    Poder.EXECUTIVO: "Executivo",
    Poder.LEGISLATIVO: "Legislativo",
    Poder.JUDICIARIO: "Judiciário",
    Poder.NAO_SE_APLICA: "Não se aplica",
}

TIPO_PESSOA = {
    TipoPessoa.JURIDICA: "Pessoa jurídica",
    TipoPessoa.FISICA: "Pessoa física",
    TipoPessoa.ESTRANGEIRA: "Pessoa estrangeira",
}

MATERIAL_OU_SERVICO = {
    MaterialOuServico.MATERIAL: "Material",
    MaterialOuServico.SERVICO: "Serviço",
}
