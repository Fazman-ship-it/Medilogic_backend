"""Add FK constraints for InternationalApplication payments

Revision ID: 02416f8ee455
Revises: 19c0b00fd8b7
Create Date: 2025-09-02 18:10:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '02416f8ee455'
down_revision = '19c0b00fd8b7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add foreign key for application_fee_payment_id in InternationalApplication
    op.create_foreign_key(
        'fk_international_applications_application_fee_payment',
        'international_applications',
        'payments',
        ['application_fee_payment_id'],
        ['id'],
        ondelete='SET NULL'
    )

    # Ensure foreign key exists for application_id in Payment
    # (optional if already exists, Alembic will ignore)
    op.create_foreign_key(
        'fk_payments_application_id',
        'payments',
        'international_applications',
        ['application_id'],
        ['id'],
        ondelete='CASCADE'
    )


def downgrade() -> None:
    op.drop_constraint(
        'fk_international_applications_application_fee_payment',
        'international_applications',
        type_='foreignkey'
    )
    op.drop_constraint(
        'fk_payments_application_id',
        'payments',
        type_='foreignkey'
    )