"""create medilogic drivers table

Revision ID: 60f5e06e6faf
Revises: 00fbaf777ab6
Create Date: 2025-08-29 07:11:39.138767

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '60f5e06e6faf'
down_revision: Union[str, Sequence[str], None] = '00fbaf777ab6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
