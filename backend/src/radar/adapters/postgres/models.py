"""Modelos SQLAlchemy 2.0: como as entidades viram tabelas no schema `silver`.

Estes modelos são detalhe de persistência e nunca saem do adapter: os repositórios
convertem para as entidades do domínio (ver `mappers.py`). Por isso eles podem ter
coisas que o domínio não tem, como o `id` numérico e as datas de auditoria.
"""

from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    MetaData,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from radar.domain.enums import (
    Esfera,
    MaterialOuServico,
    Modalidade,
    Poder,
    SituacaoContratacao,
    TipoPessoa,
)
from radar.ports.silver import MotivoRejeicao

SCHEMA = "silver"

# Nomes previsíveis para constraints e índices. Sem isso, o Postgres inventa nomes
# e o Alembic não consegue achar a constraint certa para alterar ou remover depois.
NAMING_CONVENTION = {
    "pk": "pk_%(table_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
}

# numeric(18, 4): até 14 dígitos inteiros e 4 decimais, exato (nunca float)
Money = Numeric(18, 4)


def _in_check(column: str, enum: Iterable[Enum]) -> str:
    """Gera `coluna IN (...)` a partir de um Enum: o banco aceita só os códigos válidos."""
    rendered = ", ".join(
        str(member.value) if isinstance(member.value, int) else f"'{member.value}'"
        for member in enum
    )
    return f"{column} IN ({rendered})"


class Base(DeclarativeBase):
    metadata = MetaData(schema=SCHEMA, naming_convention=NAMING_CONVENTION)


class _AuditMixin:
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class OrgaoModel(_AuditMixin, Base):
    __tablename__ = "orgao"
    __table_args__ = (
        CheckConstraint(_in_check("esfera", Esfera), name="esfera_valida"),
        CheckConstraint(_in_check("poder", Poder), name="poder_valido"),
    )

    # chave substituta (surrogate): número gerado pelo banco, usado nas FKs
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    # chave natural: UNIQUE garante que o mesmo órgão nunca é gravado duas vezes
    cnpj: Mapped[str] = mapped_column(String(14), unique=True)
    razao_social: Mapped[str] = mapped_column(Text)
    esfera: Mapped[str] = mapped_column(String(1))
    poder: Mapped[str] = mapped_column(String(1))


class FornecedorModel(_AuditMixin, Base):
    __tablename__ = "fornecedor"
    __table_args__ = (CheckConstraint(_in_check("tipo_pessoa", TipoPessoa), name="tipo_valido"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    documento: Mapped[str] = mapped_column(String(30), unique=True)
    tipo_pessoa: Mapped[str] = mapped_column(String(2))
    nome: Mapped[str] = mapped_column(Text)


class ContratacaoModel(_AuditMixin, Base):
    __tablename__ = "contratacao"
    __table_args__ = (
        CheckConstraint(_in_check("modalidade", Modalidade), name="modalidade_valida"),
        CheckConstraint(_in_check("situacao", SituacaoContratacao), name="situacao_valida"),
        CheckConstraint("valor_total_estimado >= 0", name="valor_nao_negativo"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    numero_controle_pncp: Mapped[str] = mapped_column(String(30), unique=True)
    # index=True: filtrar por órgão, data e UF vai ser comum na API e no dbt
    orgao_id: Mapped[int] = mapped_column(ForeignKey(OrgaoModel.id), index=True)
    ano: Mapped[int] = mapped_column(SmallInteger)
    sequencial: Mapped[int] = mapped_column(Integer)
    modalidade: Mapped[int] = mapped_column(SmallInteger)
    situacao: Mapped[int] = mapped_column(SmallInteger)
    objeto: Mapped[str] = mapped_column(Text)
    valor_total_estimado: Mapped[Decimal | None] = mapped_column(Money)
    data_publicacao: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    uf: Mapped[str] = mapped_column(String(2), index=True)
    municipio: Mapped[str] = mapped_column(Text)

    # lazy="raise": acessar sem carregar explicitamente é erro. Evita o problema
    # "N+1" (uma consulta extra escondida para cada contratação de uma lista).
    orgao: Mapped[OrgaoModel] = relationship(lazy="raise")
    itens: Mapped[list["ItemContratacaoModel"]] = relationship(
        lazy="raise", order_by="ItemContratacaoModel.numero_item"
    )


class ItemContratacaoModel(_AuditMixin, Base):
    __tablename__ = "item_contratacao"
    __table_args__ = (
        UniqueConstraint("contratacao_id", "numero_item"),
        CheckConstraint(
            _in_check("material_ou_servico", MaterialOuServico), name="material_ou_servico_valido"
        ),
        CheckConstraint("quantidade > 0", name="quantidade_positiva"),
        CheckConstraint("valor_unitario_estimado >= 0", name="valor_estimado_nao_negativo"),
        CheckConstraint("valor_unitario_homologado >= 0", name="valor_homologado_nao_negativo"),
        # resultado do item: fornecedor e preço homologado existem juntos ou não existem
        CheckConstraint(
            "(fornecedor_id IS NULL) = (valor_unitario_homologado IS NULL)",
            name="resultado_completo",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    # CASCADE: apagar a contratação apaga seus itens (o item não existe sozinho)
    contratacao_id: Mapped[int] = mapped_column(ForeignKey(ContratacaoModel.id, ondelete="CASCADE"))
    numero_item: Mapped[int] = mapped_column(Integer)
    descricao: Mapped[str] = mapped_column(Text)
    material_ou_servico: Mapped[str] = mapped_column(String(1))
    categoria: Mapped[str | None] = mapped_column(Text)
    quantidade: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    unidade_medida: Mapped[str] = mapped_column(Text)
    # NULL = orçamento sigiloso (valor desconhecido); nunca gravar 0 no lugar
    valor_unitario_estimado: Mapped[Decimal | None] = mapped_column(Money)
    fornecedor_id: Mapped[int | None] = mapped_column(ForeignKey(FornecedorModel.id), index=True)
    valor_unitario_homologado: Mapped[Decimal | None] = mapped_column(Money)
    # NCM (8 dígitos) ou NBS (9); pode ser só o capítulo (2). Base da categoria no dbt
    ncm_nbs: Mapped[str | None] = mapped_column(String(9))

    fornecedor: Mapped[FornecedorModel | None] = relationship(lazy="raise")


class RegistroRejeitadoModel(Base):
    """Registros que não entraram na silver, com o motivo (qualidade de dados)."""

    __tablename__ = "registros_rejeitados"
    __table_args__ = (
        # NULLS NOT DISTINCT (Postgres 15+): sem isso, duas linhas com numero_item NULL
        # (rejeição da contratação inteira) não "conflitam", e reprocessar duplicaria
        UniqueConstraint(
            "numero_controle_pncp",
            "bronze_hash",
            "numero_item",
            name="uq_registros_rejeitados_versao_item",
            postgresql_nulls_not_distinct=True,
        ),
        CheckConstraint(_in_check("motivo", MotivoRejeicao), name="motivo_valido"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    fonte: Mapped[str] = mapped_column(String(20), server_default="pncp")
    # Text: o número pode vir malformado do bruto (e ser justamente o motivo da rejeição).
    # Sem index=True: o UNIQUE acima começa por esta coluna e já serve de índice para ela.
    numero_controle_pncp: Mapped[str] = mapped_column(Text)
    bronze_hash: Mapped[str] = mapped_column(String(64))
    numero_item: Mapped[int | None] = mapped_column(Integer)
    motivo: Mapped[str] = mapped_column(String(30), index=True)
    # lista de {"campo": ..., "erro": ...}; JSONB permite consultar dentro do JSON
    detalhes: Mapped[list[dict[str, str]]] = mapped_column(JSONB)
    rejeitado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PipelineWatermarkModel(Base):
    """Até onde cada pipeline incremental já processou (marca d'água)."""

    __tablename__ = "pipeline_watermark"

    pipeline: Mapped[str] = mapped_column(String(50), primary_key=True)
    marca: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
