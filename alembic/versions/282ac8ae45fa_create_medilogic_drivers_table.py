"""create medilogic drivers table

Revision ID: 282ac8ae45fa
Revises: 5c1ebe7e94fd
Create Date: 2025-08-29 07:35:37.048253

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '282ac8ae45fa'
down_revision: Union[str, Sequence[str], None] = '5c1ebe7e94fd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
