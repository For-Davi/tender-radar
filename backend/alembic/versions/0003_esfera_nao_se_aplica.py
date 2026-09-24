"""Esfera "N" (não se aplica) no órgão.

Revisão: 0003
Anterior: 0002
Criada em: 2026-09-24 21:00:00

Encontrado nos dados reais: consórcios públicos vêm com `esferaId: "N"`. O CHECK da
0001 só aceitava F/E/M/D. Escrita à mão: o autogenerate do Alembic não detecta
mudança no texto de um CHECK. Não se edita a 0001 porque ela já foi aplicada.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "orgao"
_CHECK = "ck_orgao_esfera_valida"


def upgrade() -> None:
    op.drop_constraint(op.f(_CHECK), _TABLE, type_="check", schema="silver")
    op.create_check_constraint(
        # op.f(): o nome já está completo; sem isso a convenção de nomes o prefixaria de novo
        op.f(_CHECK),
        _TABLE,
        "esfera IN ('F', 'E', 'M', 'D', 'N')",
        schema="silver",
    )


def downgrade() -> None:
    # falha se já houver órgão com esfera "N": voltar exigiria apagar ou inventar dado
    op.drop_constraint(op.f(_CHECK), _TABLE, type_="check", schema="silver")
    op.create_check_constraint(
        op.f(_CHECK), _TABLE, "esfera IN ('F', 'E', 'M', 'D')", schema="silver"
    )
