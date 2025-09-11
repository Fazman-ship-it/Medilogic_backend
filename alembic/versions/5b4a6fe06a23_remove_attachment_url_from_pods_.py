"""remove attachment_url from pods/incidents, add incident_files

Revision ID: 5b4a6fe06a23
Revises: d48d054038e9
Create Date: 2025-09-11 14:58:12.560461

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
import uuid

# revision identifiers, used by Alembic.
revision: str = '5b4a6fe06a23'
down_revision: Union[str, Sequence[str], None] = 'd48d054038e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # --- 1. Drop attachment_url from pods ---
    with op.batch_alter_table("pods") as batch_op:
        batch_op.drop_column("attachment_url")

    # --- 2. Drop attachment_url from incidents ---
    with op.batch_alter_table("incidents") as batch_op:
        batch_op.drop_column("attachment_url")

    # --- 3. Create incident_files table ---
    op.create_table(
        "incident_files",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("incident_id", sa.UUID(as_uuid=True), sa.ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("s3_key", sa.String(), nullable=False),
        sa.Column("file_type", sa.String(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    # --- Rollback: re-add attachment_url columns ---
    with op.batch_alter_table("pods") as batch_op:
        batch_op.add_column(sa.Column("attachment_url", sa.String(), nullable=True))

    with op.batch_alter_table("incidents") as batch_op:
        batch_op.add_column(sa.Column("attachment_url", sa.String(), nullable=True))

    # --- Drop incident_files table ---
    op.drop_table("incident_files")
