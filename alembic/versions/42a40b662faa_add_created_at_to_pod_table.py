"""add created_at to pods table

Revision ID: 42a40b662faa
Revises: 846a67be1c17
Create Date: 2025-09-08 17:18:01.562728

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '42a40b662faa'
down_revision: Union[str, Sequence[str], None] = '846a67be1c17'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'pods',
        sa.Column(
            'created_at',
            sa.DateTime(),
            nullable=False,
            server_default=sa.text('CURRENT_TIMESTAMP')
        )
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('pods', 'created_at')