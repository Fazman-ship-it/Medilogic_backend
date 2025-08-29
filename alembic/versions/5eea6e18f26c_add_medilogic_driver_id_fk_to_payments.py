"""add medilogic_driver_id FK to payments

Revision ID: 5eea6e18f26c
Revises: d8ca607887a9
Create Date: 2025-08-29 08:13:03.670200

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5eea6e18f26c'
down_revision: Union[str, Sequence[str], None] = 'd8ca607887a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
