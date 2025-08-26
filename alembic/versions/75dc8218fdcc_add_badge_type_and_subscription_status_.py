"""Add badge_type and subscription_status enums

Revision ID: 75dc8218fdcc
Revises: 86201b08a3f9
Create Date: 2025-08-26 04:10:13.063346
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '75dc8218fdcc'
down_revision: Union[str, Sequence[str], None] = '86201b08a3f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create new table for application views
    op.create_table(
        'application_views',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('application_id', sa.UUID(), nullable=False),
        sa.Column('organization_id', sa.UUID(), nullable=False),
        sa.Column('viewed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['application_id'], ['international_applications.id']),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.PrimaryKeyConstraint('id')
    )

    # Add badge_type enum
    badge_type_enum = sa.Enum('none', 'green', 'blue', name='badgetype')
    badge_type_enum.create(op.get_bind(), checkfirst=True)
    op.add_column('international_applications',
        sa.Column('badge_type', badge_type_enum, nullable=False, server_default='none')
    )

    # Add subscription_status enum
    subscription_status_enum = sa.Enum('active', 'expired', 'cancelled', name='subscriptionstatus')
    subscription_status_enum.create(op.get_bind(), checkfirst=True)
    op.add_column('international_applications',
        sa.Column('subscription_status', subscription_status_enum, nullable=False, server_default='expired')
    )

    # Add subscription dates
    op.add_column('international_applications', sa.Column('subscription_start_date', sa.DateTime(), nullable=True))
    op.add_column('international_applications', sa.Column('subscription_end_date', sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Drop added columns
    op.drop_column('international_applications', 'subscription_end_date')
    op.drop_column('international_applications', 'subscription_start_date')
    op.drop_column('international_applications', 'subscription_status')
    op.drop_column('international_applications', 'badge_type')

    # Drop enums explicitly
    sa.Enum(name='subscriptionstatus').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='badgetype').drop(op.get_bind(), checkfirst=True)

    # Drop table
    op.drop_table('application_views')