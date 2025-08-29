"""create documents and driver_views

Revision ID: d8ca607887a9
Revises: 282ac8ae45fa
Create Date: 2025-08-29 07:37:43.790933

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd8ca607887a9'
down_revision: Union[str, Sequence[str], None] = '282ac8ae45fa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
