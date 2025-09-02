"""Add Stripe and payment fields

Revision ID: 6d5e94a3927a
Revises: 447c0411f846
Create Date: 2025-09-02 15:12:30.418087

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
import sqlalchemy.dialects.postgresql as pg

# revision identifiers, used by Alembic.
revision: str = '6d5e94a3927a'
down_revision: Union[str, Sequence[str], None] = '447c0411f846'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ----- InternationalApplication table -----
    op.add_column('international_applications', sa.Column('stripe_customer_id', sa.String(), nullable=True))
    op.add_column('international_applications', sa.Column('stripe_subscription_id', sa.String(), nullable=True))
    op.add_column('international_applications', sa.Column('stripe_price_id', sa.String(), nullable=True))
    op.add_column('international_applications', sa.Column('cancel_at_period_end', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('international_applications', sa.Column('application_fee_payment_id', pg.UUID(), nullable=True))

    # Foreign key for application_fee_payment_id
    op.create_foreign_key(
        'fk_application_fee_payment',
        'international_applications', 'payments',
        ['application_fee_payment_id'], ['id'],
        ondelete='SET NULL'
    )

    # ----- Payment table -----
    op.add_column('payments', sa.Column('payment_type', sa.String(), nullable=False, server_default='one_time'))


def downgrade() -> None:
    """Downgrade schema."""
    # ----- InternationalApplication table -----
    op.drop_constraint('fk_application_fee_payment', 'international_applications', type_='foreignkey')
    op.drop_column('international_applications', 'application_fee_payment_id')
    op.drop_column('international_applications', 'stripe_customer_id')
    op.drop_column('international_applications', 'stripe_subscription_id')
    op.drop_column('international_applications', 'stripe_price_id')
    op.drop_column('international_applications', 'cancel_at_period_end')

    # ----- Payment table -----
    op.drop_column('payments', 'payment_type')