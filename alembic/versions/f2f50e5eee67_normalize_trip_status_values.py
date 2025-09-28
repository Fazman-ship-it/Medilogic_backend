"""Normalize trip status values

Revision ID: f2f50e5eee67
Revises: f444da24a437
Create Date: 2025-09-28 17:43:20.182260
"""
from typing import Sequence, Union
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f2f50e5eee67'
down_revision: Union[str, Sequence[str], None] = 'f444da24a437'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Normalize status values to lowercase and underscores."""
    op.execute("""
        UPDATE trips
        SET status = LOWER(REPLACE(status, ' ', '_'));
    """)


def downgrade() -> None:
    """Revert status values to capitalized words (best-effort)."""
    op.execute("""
        UPDATE trips
        SET status = INITCAP(REPLACE(status, '_', ' '));
    """)