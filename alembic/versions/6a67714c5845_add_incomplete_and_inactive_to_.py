"""add incomplete and inactive to subscriptionstatus enum

Revision ID: 6a67714c5845
Revises: 6c24c715a620
Create Date: 2026-04-12 14:28:00.230973
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6a67714c5845'
down_revision: Union[str, Sequence[str], None] = '6c24c715a620'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # ✅ Add missing enum values (safe for production)
    op.execute(
        "ALTER TYPE subscriptionstatus ADD VALUE IF NOT EXISTS 'inactive';"
    )

    op.execute(
        "ALTER TYPE subscriptionstatus ADD VALUE IF NOT EXISTS 'incomplete';"
    )


def downgrade() -> None:
    """Downgrade schema."""

    # ⚠️ PostgreSQL does NOT support removing enum values safely
    # So we leave this empty intentionally
    pass