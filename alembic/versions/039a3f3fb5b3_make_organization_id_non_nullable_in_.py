"""Make organization_id non-nullable in compliance_statuses

Revision ID: 039a3f3fb5b3
Revises: 5f75b35d2989
Create Date: 2025-11-12 15:47:11.890120
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '039a3f3fb5b3'
down_revision = '5f75b35d2989'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade schema."""

    # 1️⃣ Make sure there are no NULL organization_ids
    # If your table is clean and all rows already have a value, you can skip this step
    op.execute("""
        UPDATE compliance_statuses
        SET organization_id = '00000000-0000-0000-0000-000000000000'
        WHERE organization_id IS NULL
    """)

    # 2️⃣ Alter column to be non-nullable
    op.alter_column(
        'compliance_statuses',
        'organization_id',
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False
    )


def downgrade() -> None:
    """Downgrade schema."""

    # Make the column nullable again
    op.alter_column(
        'compliance_statuses',
        'organization_id',
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True
    )