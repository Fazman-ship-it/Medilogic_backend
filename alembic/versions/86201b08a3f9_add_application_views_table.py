"""add application_views table

Revision ID: 86201b08a3f9
Revises: f8f1c740f25f
Create Date: 2025-08-25 22:03:02.517520

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '86201b08a3f9'
down_revision: Union[str, Sequence[str], None] = 'f8f1c740f25f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
