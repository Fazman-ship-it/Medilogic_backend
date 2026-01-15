"""Make medilogic drivers application fields nullable

Revision ID: 4f844940fe40
Revises: 07915e73b2cd
Create Date: 2026-01-15 22:24:46.222573

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4f844940fe40"
down_revision = "07915e73b2cd"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Make application-only fields nullable for Option A flow
    op.alter_column(
        "medilogic_drivers",
        "license_number",
        existing_type=sa.String(),
        nullable=True,
    )
    op.alter_column(
        "medilogic_drivers",
        "license_expiry",
        existing_type=sa.Date(),
        nullable=True,
    )
    op.alter_column(
        "medilogic_drivers",
        "vehicle_type",
        existing_type=sa.String(),
        nullable=True,
    )
    op.alter_column(
        "medilogic_drivers",
        "preferred_role",
        existing_type=sa.String(),
        nullable=True,
    )


def downgrade() -> None:
    # ⚠️ Downgrade can fail if rows contain NULLs.
    op.alter_column(
        "medilogic_drivers",
        "license_number",
        existing_type=sa.String(),
        nullable=False,
    )
    op.alter_column(
        "medilogic_drivers",
        "license_expiry",
        existing_type=sa.Date(),
        nullable=False,
    )
    op.alter_column(
        "medilogic_drivers",
        "vehicle_type",
        existing_type=sa.String(),
        nullable=False,
    )
    op.alter_column(
        "medilogic_drivers",
        "preferred_role",
        existing_type=sa.String(),
        nullable=False,
    )