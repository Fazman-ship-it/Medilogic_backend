"""make datetime utc aware

Revision ID: fd04a8dcbb69
Revises: e293ec8c16d8
Create Date: 2025-10-02 14:36:28.693990
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'fd04a8dcbb69'
down_revision = 'e293ec8c16d8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Empty upgrade - fill later
    pass


def downgrade() -> None:
    # Empty downgrade - fill later
    pass