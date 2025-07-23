"""add last_location_update to users and driver location history

Revision ID: e94b591a4a5b
Revises: 7ed52e490e23
Create Date: 2025-07-22 21:55:09.323059
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e94b591a4a5b'
down_revision: Union[str, Sequence[str], None] = '7ed52e490e23'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ✅ Create the Enum type explicitly first
    custody_event_enum = sa.Enum(
        'pickup_confirmed', 'in_transit', 'delayed', 'handed_off', 'delivered',
        name='custodyeventtype'
    )
    custody_event_enum.create(op.get_bind(), checkfirst=True)

    # ✅ Create driver_location_history table
    op.create_table(
        'driver_location_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('driver_id', sa.Integer(), nullable=True),
        sa.Column('latitude', sa.Float(), nullable=False),
        sa.Column('longitude', sa.Float(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['driver_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_driver_location_history_id'), 'driver_location_history', ['id'], unique=False)

    # ✅ Add new fields
    op.add_column('users', sa.Column('last_location_update', sa.DateTime(), nullable=True))
    op.add_column('chain_of_custody', sa.Column('event_type', custody_event_enum, nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    # ✅ Drop the new fields
    op.drop_column('users', 'last_location_update')
    op.drop_column('chain_of_custody', 'event_type')

    # ✅ Drop driver_location_history table
    op.drop_index(op.f('ix_driver_location_history_id'), table_name='driver_location_history')
    op.drop_table('driver_location_history')

    # ✅ Drop the Enum type
    custody_event_enum = sa.Enum(
        'pickup_confirmed', 'in_transit', 'delayed', 'handed_off', 'delivered',
        name='custodyeventtype'
    )
    custody_event_enum.drop(op.get_bind(), checkfirst=True)