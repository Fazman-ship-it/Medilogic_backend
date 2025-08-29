"""create _medilogic_drivers table _add_documents_and_analytics

Revision ID: da92743486ec
Revises: 40289db61693
Create Date: 2025-08-29 02:06:14.137801

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'da92743486ec'
down_revision: Union[str, Sequence[str], None] = '40289db61693'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
