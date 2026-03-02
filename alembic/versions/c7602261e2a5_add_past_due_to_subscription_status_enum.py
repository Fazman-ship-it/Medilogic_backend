"""add past_due to subscription status enum

Revision ID: c7602261e2a5
Revises: 5dd0b241c09c
Create Date: 2026-03-02 18:32:17.600449
"""

from typing import Sequence, Union
from alembic import op

# revision identifiers
revision: str = 'c7602261e2a5'
down_revision: Union[str, Sequence[str], None] = '5dd0b241c09c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nothing related to payments
    pass


def downgrade() -> None:
    pass