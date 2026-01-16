"""Make medilogic_drivers.state nullable

Revision ID: 45d5d6bedb9f
Revises: 4f844940fe40
Create Date: 2026-01-16 21:25:19.089129
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '45d5d6bedb9f'
down_revision: Union[str, Sequence[str], None] = '4f844940fe40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ✅ MAKE state nullable
    op.alter_column(
        "medilogic_drivers",
        "state",
        existing_type=sa.String(),
        nullable=True,
    )


def downgrade() -> None:
    # ⬅️ rollback (optional but correct)
    op.alter_column(
        "medilogic_drivers",
        "state",
        existing_type=sa.String(),
        nullable=False,
    )