"""add pdf_receipt_path to delivery_confirmations

Revision ID: f444da24a437
Revises: 061c53d67e3b
Create Date: 2025-09-12 09:27:57.297293

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'f444da24a437'
down_revision = '061c53d67e3b'
branch_labels = None
depends_on = None

def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "delivery_confirmations",
        sa.Column("pdf_receipt_path", sa.String(), nullable=True)
    )

def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("delivery_confirmations", "pdf_receipt_path")