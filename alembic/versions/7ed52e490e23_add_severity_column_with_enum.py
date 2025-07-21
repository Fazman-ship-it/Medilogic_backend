"""Add severity column with enum

Revision ID: 7ed52e490e23
Revises: 6def9e525b58
Create Date: 2025-07-21 14:42:00.081492
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '7ed52e490e23'
down_revision: Union[str, Sequence[str], None] = '6def9e525b58'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # Enum for severity
    severity_enum = sa.Enum('low', 'moderate', 'critical', name='severitylevel')
    severity_enum.create(op.get_bind(), checkfirst=True)

    # Enum for custody event (already exists in DB, so checkfirst=True is critical)
    #custody_event_enum = sa.Enum(
        #'pickup_confirmed', 'in_transit', 'delayed', 'handed_off', 'delivered',
       # name='custodyeventtype'
    #)
    #custody_event_enum.create(op.get_bind(), checkfirst=True)

    # Create chain_of_custody table
    op.create_table(
        'chain_of_custody',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('trip_id', sa.Integer(), nullable=False),
        sa.Column('driver_id', sa.Integer(), nullable=True),
        
        sa.Column('timestamp', sa.DateTime(), nullable=True),
        sa.Column('location', sa.String(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('attachment_url', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('signed_by', sa.String(), nullable=True),
        sa.Column('signature_image_url', sa.String(), nullable=True),
        sa.Column('signature_timestamp', sa.DateTime(), nullable=True),
        sa.Column('witness_name', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['driver_id'], ['users.id']),
        sa.ForeignKeyConstraint(['trip_id'], ['trips.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_chain_of_custody_id'), 'chain_of_custody', ['id'], unique=False)

    # Add new fields to incidents table
    op.add_column('incidents', sa.Column('severity', severity_enum, nullable=False, server_default='low'))
    op.add_column('incidents', sa.Column('escalated', sa.Boolean(), nullable=True))
    op.add_column('incidents', sa.Column('is_visible_to_regulator', sa.Boolean(), nullable=True))

    # Add session fields to users table
    op.add_column('users', sa.Column('session_id', sa.String(), nullable=True))
    op.add_column('users', sa.Column('session_expires_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'session_expires_at')
    op.drop_column('users', 'session_id')

    op.drop_column('incidents', 'is_visible_to_regulator')
    op.drop_column('incidents', 'escalated')
    op.drop_column('incidents', 'severity')

    op.drop_index(op.f('ix_chain_of_custody_id'), table_name='chain_of_custody')
    op.drop_table('chain_of_custody')

    sa.Enum(name='severitylevel').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='custodyeventtype').drop(op.get_bind(), checkfirst=True)