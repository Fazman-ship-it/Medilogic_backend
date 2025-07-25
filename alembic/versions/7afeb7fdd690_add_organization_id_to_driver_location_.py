"""Add organization_id to driver_location_history

Revision ID: 7afeb7fdd690
Revises: 30c7c98f8b65
Create Date: 2025-07-24 18:42:32.182757

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7afeb7fdd690'
down_revision: Union[str, Sequence[str], None] = '30c7c98f8b65'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
