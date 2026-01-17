"""Make users.is_superuser default false

Revision ID: 79d1c3e4c138
Revises: 6e9dcc10e06a
Create Date: 2026-01-17 19:45:20.165695

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '79d1c3e4c138'
down_revision: Union[str, Sequence[str], None] = '6e9dcc10e06a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Set DB-level default to false
    op.alter_column(
        "users",
        "is_superuser",
        server_default=sa.text("false"),
        existing_type=sa.Boolean(),
        existing_nullable=False,
    )

def downgrade() -> None:
    # Revert DB-level default to true (old behaviour)
    op.alter_column(
        "users",
        "is_superuser",
        server_default=sa.text("true"),
        existing_type=sa.Boolean(),
        existing_nullable=False,
    )