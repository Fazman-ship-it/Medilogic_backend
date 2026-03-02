"""add past_due to subscription status enum

Revision ID: 3f490ff9eb4f
Revises: c7602261e2a5
Create Date: 2026-03-02 18:46:46.063665
"""

from typing import Sequence, Union
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '3f490ff9eb4f'
down_revision: Union[str, Sequence[str], None] = 'c7602261e2a5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add 'past_due' value to existing PostgreSQL enum type.
    """
    op.execute(
        "ALTER TYPE subscriptionstatus ADD VALUE IF NOT EXISTS 'past_due';"
    )


def downgrade() -> None:
    """
    PostgreSQL does not support removing enum values safely.
    Leaving empty intentionally.
    """
    pass