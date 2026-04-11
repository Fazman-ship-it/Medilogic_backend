
"""add subscription table

Revision ID: f593b4227227
Revises: 022ce60654c3
Create Date: 2026-04-11
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


# revision identifiers
revision: str = 'f593b4227227'
down_revision: Union[str, Sequence[str], None] = '022ce60654c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    # ✅ SKIP IF TABLE EXISTS
    if "subscriptions" in inspector.get_table_names():
        print("✅ subscriptions table already exists — skipping")
        return

    # ✅ USE EXISTING POSTGRES ENUM (NO CREATION)
    subscription_status_enum = postgresql.ENUM(
        'active',
        'expired',
        'cancelled',
        'none',
        'past_due',
        'inactive',
        name='subscriptionstatus',
        create_type=False  # 🔥 THIS STOPS DUPLICATION
    )

    # ✅ CREATE TABLE
    op.create_table(
        'subscriptions',

        sa.Column(
            'id',
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False
        ),

        sa.Column(
            'org_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('organizations.id', ondelete='CASCADE'),
            nullable=False
        ),

        sa.Column(
            'stripe_subscription_id',
            sa.String(),
            nullable=False,
            unique=True
        ),

        sa.Column(
            'status',
            subscription_status_enum,
            nullable=False
        ),

        sa.Column(
            'current_period_end',
            sa.DateTime(),
            nullable=True
        ),

        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=True
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if "subscriptions" in inspector.get_table_names():
        op.drop_table('subscriptions')