"""Schemas Pydantic do JSON bruto do PNCP (entrada do bronze -> silver).

Primeira camada de validação: formato e completude. Aponta o caminho do campo
(`orgaoEntidade.cnpj`) quando algo está ausente ou não se converte. As regras de
negócio ficam para as entidades do domínio (segunda camada).

- `extra="ignore"`: o PNCP tem dezenas de campos que a silver não usa;
- os tipos `Texto`, `Valor`... aplicam as funções de `normalizacao.py` ANTES da
  validação do Pydantic (`BeforeValidator`), então o Pydantic recebe o valor limpo.
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from radar.domain.enums import (
    Esfera,
    MaterialOuServico,
    Modalidade,
    Poder,
    SituacaoContratacao,
    TipoPessoa,
)
from radar.pipelines.normalizacao import (
    normalizar_categoria,
    normalizar_texto,
    para_datetime,
    para_decimal,
    para_decimal_opcional,
    texto_obrigatorio,
)
from radar.ports.contratacoes_source import JsonDict

Texto = Annotated[str, BeforeValidator(texto_obrigatorio)]
TextoOpcional = Annotated[str | None, BeforeValidator(normalizar_texto)]
Categoria = Annotated[str | None, BeforeValidator(normalizar_categoria)]
Valor = Annotated[Decimal, BeforeValidator(para_decimal)]
ValorOpcional = Annotated[Decimal | None, BeforeValidator(para_decimal_opcional)]
DataHora = Annotated[datetime, BeforeValidator(para_datetime)]


class _Bruto(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)


class OrgaoBronze(_Bruto):
    cnpj: Texto
    razao_social: Texto = Field(alias="razaoSocial")
    esfera: Esfera = Field(alias="esferaId")
    poder: Poder = Field(alias="poderId")


class UnidadeOrgaoBronze(_Bruto):
    uf: Texto = Field(alias="ufSigla")
    municipio: Texto = Field(alias="municipioNome")


class ContratacaoBronze(_Bruto):
    numero_controle_pncp: Texto = Field(alias="numeroControlePNCP")
    orgao: OrgaoBronze = Field(alias="orgaoEntidade")
    unidade: UnidadeOrgaoBronze = Field(alias="unidadeOrgao")
    modalidade: Modalidade = Field(alias="modalidadeId")
    situacao: SituacaoContratacao = Field(alias="situacaoCompraId")
    objeto: Texto = Field(alias="objetoCompra")
    valor_total_estimado: ValorOpcional = Field(alias="valorTotalEstimado", default=None)
    data_publicacao: DataHora = Field(alias="dataPublicacaoPncp")


class ItemBronze(_Bruto):
    numero_item: int = Field(alias="numeroItem")
    descricao: Texto
    material_ou_servico: MaterialOuServico = Field(alias="materialOuServico")
    categoria: Categoria = Field(alias="itemCategoriaNome", default=None)
    quantidade: Valor
    unidade_medida: Texto = Field(alias="unidadeMedida")
    valor_unitario_estimado: ValorOpcional = Field(alias="valorUnitarioEstimado", default=None)
    orcamento_sigiloso: bool = Field(alias="orcamentoSigiloso", default=False)


class ResultadoBronze(_Bruto):
    ni_fornecedor: Texto = Field(alias="niFornecedor")
    tipo_pessoa: TipoPessoa = Field(alias="tipoPessoa")
    nome_fornecedor: Texto = Field(alias="nomeRazaoSocialFornecedor")
    valor_unitario_homologado: Valor = Field(alias="valorUnitarioHomologado")
    data_cancelamento: TextoOpcional = Field(alias="dataCancelamento", default=None)
    ordem_classificacao_srp: int | None = Field(alias="ordemClassificacaoSrp", default=None)
    sequencial_resultado: int = Field(alias="sequencialResultado", default=0)


class PayloadBronze(_Bruto):
    """O documento da bronze. Itens e resultados ficam crus aqui de propósito: são
    validados um a um, para que um item ruim não derrube a contratação inteira."""

    contratacao: JsonDict
    itens: list[JsonDict] = []
    # chave = número do item consultado (texto, porque chave de JSON é sempre texto)
    resultados: dict[str, list[JsonDict]] = {}
