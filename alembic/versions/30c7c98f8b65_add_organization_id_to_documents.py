"""Add organization_id to documents

Revision ID: 30c7c98f8b65
Revises: d809102740b8
Create Date: 2025-07-24 18:09:47.802184

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '30c7c98f8b65'
down_revision: Union[str, Sequence[str], None] = 'd809102740b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
