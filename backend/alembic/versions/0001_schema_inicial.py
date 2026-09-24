"""Schema inicial da camada silver: orgao, fornecedor, contratacao e item_contratacao.

Gerada com `alembic revision --autogenerate` e revisada à mão. Ajuste manual:
criação e remoção do schema `silver` (o autogenerate só cria tabelas).

Revisão: 0001
Anterior: nenhuma
Criada em: 2026-09-24 16:19:47.757916
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS silver")
    op.create_table(
        "fornecedor",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("documento", sa.String(length=30), nullable=False),
        sa.Column("tipo_pessoa", sa.String(length=2), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "tipo_pessoa IN ('PJ', 'PF', 'PE')", name=op.f("ck_fornecedor_tipo_valido")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fornecedor")),
        sa.UniqueConstraint("documento", name=op.f("uq_fornecedor_documento")),
        schema="silver",
    )
    op.create_table(
        "orgao",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("cnpj", sa.String(length=14), nullable=False),
        sa.Column("razao_social", sa.Text(), nullable=False),
        sa.Column("esfera", sa.String(length=1), nullable=False),
        sa.Column("poder", sa.String(length=1), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("esfera IN ('F', 'E', 'M', 'D')", name=op.f("ck_orgao_esfera_valida")),
        sa.CheckConstraint("poder IN ('E', 'L', 'J', 'N')", name=op.f("ck_orgao_poder_valido")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_orgao")),
        sa.UniqueConstraint("cnpj", name=op.f("uq_orgao_cnpj")),
        schema="silver",
    )
    op.create_table(
        "contratacao",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("numero_controle_pncp", sa.String(length=30), nullable=False),
        sa.Column("orgao_id", sa.BigInteger(), nullable=False),
        sa.Column("ano", sa.SmallInteger(), nullable=False),
        sa.Column("sequencial", sa.Integer(), nullable=False),
        sa.Column("modalidade", sa.SmallInteger(), nullable=False),
        sa.Column("situacao", sa.SmallInteger(), nullable=False),
        sa.Column("objeto", sa.Text(), nullable=False),
        sa.Column("valor_total_estimado", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("data_publicacao", sa.DateTime(timezone=True), nullable=False),
        sa.Column("uf", sa.String(length=2), nullable=False),
        sa.Column("municipio", sa.Text(), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "modalidade IN (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13)",
            name=op.f("ck_contratacao_modalidade_valida"),
        ),
        sa.CheckConstraint("situacao IN (1, 2, 3, 4)", name=op.f("ck_contratacao_situacao_valida")),
        sa.CheckConstraint(
            "valor_total_estimado >= 0", name=op.f("ck_contratacao_valor_nao_negativo")
        ),
        sa.ForeignKeyConstraint(
            ["orgao_id"], ["silver.orgao.id"], name=op.f("fk_contratacao_orgao_id")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contratacao")),
        sa.UniqueConstraint(
            "numero_controle_pncp", name=op.f("uq_contratacao_numero_controle_pncp")
        ),
        schema="silver",
    )
    op.create_index(
        op.f("ix_contratacao_data_publicacao"),
        "contratacao",
        ["data_publicacao"],
        unique=False,
        schema="silver",
    )
    op.create_index(
        op.f("ix_contratacao_orgao_id"), "contratacao", ["orgao_id"], unique=False, schema="silver"
    )
    op.create_index(op.f("ix_contratacao_uf"), "contratacao", ["uf"], unique=False, schema="silver")
    op.create_table(
        "item_contratacao",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("contratacao_id", sa.BigInteger(), nullable=False),
        sa.Column("numero_item", sa.Integer(), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=False),
        sa.Column("material_ou_servico", sa.String(length=1), nullable=False),
        sa.Column("categoria", sa.Text(), nullable=True),
        sa.Column("quantidade", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("unidade_medida", sa.Text(), nullable=False),
        sa.Column("valor_unitario_estimado", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("fornecedor_id", sa.BigInteger(), nullable=True),
        sa.Column("valor_unitario_homologado", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "material_ou_servico IN ('M', 'S')",
            name=op.f("ck_item_contratacao_material_ou_servico_valido"),
        ),
        sa.CheckConstraint(
            "(fornecedor_id IS NULL) = (valor_unitario_homologado IS NULL)",
            name=op.f("ck_item_contratacao_resultado_completo"),
        ),
        sa.CheckConstraint("quantidade > 0", name=op.f("ck_item_contratacao_quantidade_positiva")),
        sa.CheckConstraint(
            "valor_unitario_estimado >= 0",
            name=op.f("ck_item_contratacao_valor_estimado_nao_negativo"),
        ),
        sa.CheckConstraint(
            "valor_unitario_homologado >= 0",
            name=op.f("ck_item_contratacao_valor_homologado_nao_negativo"),
        ),
        sa.ForeignKeyConstraint(
            ["contratacao_id"],
            ["silver.contratacao.id"],
            name=op.f("fk_item_contratacao_contratacao_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["fornecedor_id"],
            ["silver.fornecedor.id"],
            name=op.f("fk_item_contratacao_fornecedor_id"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_item_contratacao")),
        sa.UniqueConstraint(
            "contratacao_id",
            "numero_item",
            name=op.f("uq_item_contratacao_contratacao_id_numero_item"),
        ),
        schema="silver",
    )
    op.create_index(
        op.f("ix_item_contratacao_fornecedor_id"),
        "item_contratacao",
        ["fornecedor_id"],
        unique=False,
        schema="silver",
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_item_contratacao_fornecedor_id"), table_name="item_contratacao", schema="silver"
    )
    op.drop_table("item_contratacao", schema="silver")
    op.drop_index(op.f("ix_contratacao_uf"), table_name="contratacao", schema="silver")
    op.drop_index(op.f("ix_contratacao_orgao_id"), table_name="contratacao", schema="silver")
    op.drop_index(op.f("ix_contratacao_data_publicacao"), table_name="contratacao", schema="silver")
    op.drop_table("contratacao", schema="silver")
    op.drop_table("orgao", schema="silver")
    op.drop_table("fornecedor", schema="silver")
    # sem CASCADE: se outra migração deixou algo no schema, o erro avisa em vez de apagar
    op.execute("DROP SCHEMA silver")
