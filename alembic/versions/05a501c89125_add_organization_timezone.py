"""add organization.timezone

Revision ID: 05a501c89125
Revises: e770ace1100f
Create Date: 2025-12-03 21:35:10.423610

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '05a501c89125'
down_revision: Union[str, Sequence[str], None] = 'e770ace1100f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. Add column as nullable
    op.add_column(
        'organizations',
        sa.Column('timezone', sa.String(), nullable=True)
    )

    # 2. Set UTC for all existing rows
    op.execute("UPDATE organizations SET timezone = 'UTC' WHERE timezone IS NULL")

    # 3. Make it NOT NULL
    op.alter_column('organizations', 'timezone', nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('organizations', 'timezone')