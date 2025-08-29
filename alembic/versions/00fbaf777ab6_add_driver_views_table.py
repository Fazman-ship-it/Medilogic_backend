"""add_driver_views_table

Revision ID: 00fbaf777ab6
Revises: da92743486ec
Create Date: 2025-08-29 02:07:03.209065

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '00fbaf777ab6'
down_revision: Union[str, Sequence[str], None] = 'da92743486ec'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
