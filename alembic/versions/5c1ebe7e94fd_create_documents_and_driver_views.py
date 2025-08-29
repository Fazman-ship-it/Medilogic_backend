"""create documents and driver_views

Revision ID: 5c1ebe7e94fd
Revises: 60f5e06e6faf
Create Date: 2025-08-29 07:14:12.305865

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5c1ebe7e94fd'
down_revision: Union[str, Sequence[str], None] = '60f5e06e6faf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
