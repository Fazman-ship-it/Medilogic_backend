"""convert subscription_status to enum

Revision ID: 022ce60654c3
Revises: e5addbab9893
Create Date: 2026-04-07
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = '022ce60654c3'
down_revision: Union[str, Sequence[str], None] = 'e5addbab9893'
branch_labels = None
depends_on = None


# ✅ DEFINE ENUM
subscription_enum = sa.Enum(
    'active',
    'expired',
    'cancelled',
    'none',
    'past_due',
    'inactive',
    name='subscriptionstatus'
)


def upgrade() -> None:
    # 1️⃣ Create ENUM type in Postgres
    subscription_enum.create(op.get_bind(), checkfirst=True)

    # 2️⃣ Convert column using explicit cast
    op.execute("""
        ALTER TABLE organizations
        ALTER COLUMN subscription_status
        TYPE subscriptionstatus
        USING subscription_status::subscriptionstatus
    """)


def downgrade() -> None:
    # 1️⃣ Convert back to string
    op.execute("""
        ALTER TABLE organizations
        ALTER COLUMN subscription_status
        TYPE VARCHAR
    """)

    # 2️⃣ Drop ENUM
    subscription_enum.drop(op.get_bind(), checkfirst=True)