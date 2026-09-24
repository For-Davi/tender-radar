"""Código NCM/NBS no item da contratação.

Revisão: 0004
Anterior: 0003
Criada em: 2026-09-24 21:40:00

Gerada com autogenerate (sem ajustes além do formato). A coluna é anulável: o PNCP só
informa o código em parte dos itens (~23% nos dados reais). É a base da dimensão de
categoria da camada gold (Etapa 04), já que `itemCategoriaNome` vem sempre "Não se aplica".
Itens já gravados ficam com NULL até o próximo `make pipeline-completo`.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "item_contratacao",
        sa.Column("ncm_nbs", sa.String(length=9), nullable=True),
        schema="silver",
    )


def downgrade() -> None:
    op.drop_column("item_contratacao", "ncm_nbs", schema="silver")
