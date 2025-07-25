"""Add organization_id to chain_of_custody

Revision ID: a48694900231
Revises: 7afeb7fdd690
Create Date: 2025-07-24 18:59:51.674835

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a48694900231'
down_revision: Union[str, Sequence[str], None] = '7afeb7fdd690'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
