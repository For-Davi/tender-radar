"""Registros rejeitados, marca d'água dos pipelines e valor estimado anulável.

Revisão: 0002
Anterior: 0001
Criada em: 2026-09-24 17:35:44.001576

Gerada com autogenerate e revisada à mão:
- removido o índice em `registros_rejeitados.numero_controle_pncp`: o UNIQUE
  (numero_controle_pncp, bronze_hash, numero_item) já começa por essa coluna;
- `valor_unitario_estimado` anulável: NULL = orçamento sigiloso (desconhecido).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pipeline_watermark",
        sa.Column("pipeline", sa.String(length=50), nullable=False),
        sa.Column("marca", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("pipeline", name=op.f("pk_pipeline_watermark")),
        schema="silver",
    )
    op.create_table(
        "registros_rejeitados",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("fonte", sa.String(length=20), server_default="pncp", nullable=False),
        sa.Column("numero_controle_pncp", sa.Text(), nullable=False),
        sa.Column("bronze_hash", sa.String(length=64), nullable=False),
        sa.Column("numero_item", sa.Integer(), nullable=True),
        sa.Column("motivo", sa.String(length=30), nullable=False),
        sa.Column("detalhes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "rejeitado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "motivo IN ('campo_invalido', 'regra_negocio', 'item_duplicado', "
            "'resultado_invalido', 'persistencia')",
            name=op.f("ck_registros_rejeitados_motivo_valido"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_registros_rejeitados")),
        sa.UniqueConstraint(
            "numero_controle_pncp",
            "bronze_hash",
            "numero_item",
            name="uq_registros_rejeitados_versao_item",
            postgresql_nulls_not_distinct=True,
        ),
        schema="silver",
    )
    op.create_index(
        op.f("ix_registros_rejeitados_motivo"),
        "registros_rejeitados",
        ["motivo"],
        unique=False,
        schema="silver",
    )
    op.alter_column(
        "item_contratacao",
        "valor_unitario_estimado",
        existing_type=sa.NUMERIC(precision=18, scale=4),
        nullable=True,
        schema="silver",
    )


def downgrade() -> None:
    # Falha de propósito se houver itens sigilosos (NULL): voltar exigiria inventar um
    # valor (0) para eles, que é exatamente o erro que esta migração evita.
    op.alter_column(
        "item_contratacao",
        "valor_unitario_estimado",
        existing_type=sa.NUMERIC(precision=18, scale=4),
        nullable=False,
        schema="silver",
    )
    op.drop_index(
        op.f("ix_registros_rejeitados_motivo"),
        table_name="registros_rejeitados",
        schema="silver",
    )
    op.drop_table("registros_rejeitados", schema="silver")
    op.drop_table("pipeline_watermark", schema="silver")
