"""Schemas Pydantic das respostas do PNCP.

Validam SÓ os campos que o sistema usa para decidir algo (chaves, paginação, se o
documento é edital). `extra="ignore"`: o PNCP ganha campos novos com frequência, e
isso não pode quebrar a ingestão; o registro completo segue bruto para a bronze.
"""

from pydantic import BaseModel, ConfigDict, Field

# tipoDocumentoId do PNCP para "Edital" (tabela de domínio "Tipo de Documento")
TIPO_DOCUMENTO_EDITAL = 2


class _PncpModel(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)


class OrgaoEntidade(_PncpModel):
    cnpj: str = Field(min_length=14, max_length=14)


class ContratacaoPublicada(_PncpModel):
    numero_controle_pncp: str = Field(alias="numeroControlePNCP", min_length=1)
    orgao_entidade: OrgaoEntidade = Field(alias="orgaoEntidade")
    ano_compra: int = Field(alias="anoCompra")
    sequencial_compra: int = Field(alias="sequencialCompra")


class PaginaPublicacao(_PncpModel):
    # os registros são validados um a um depois (para o erro apontar qual registro falhou)
    data: list[dict[str, object]]
    paginas_restantes: int = Field(alias="paginasRestantes", ge=0)


class ItemPncp(_PncpModel):
    numero_item: int = Field(alias="numeroItem")
    tem_resultado: bool = Field(alias="temResultado")


class ArquivoPncp(_PncpModel):
    sequencial_documento: int = Field(alias="sequencialDocumento")
    tipo_documento_id: int = Field(alias="tipoDocumentoId")
    url: str = Field(min_length=1)
