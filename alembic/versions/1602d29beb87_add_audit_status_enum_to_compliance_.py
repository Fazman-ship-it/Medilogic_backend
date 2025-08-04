"""Add audit_status enum to compliance_status; create notifications table"""

from alembic import op
import sqlalchemy as sa
import enum
from sqlalchemy.dialects import postgresql
from uuid import uuid4

# Revision identifiers, used by Alembic.
revision = '1602d29beb87'
down_revision = '4cc8c3199150'
branch_labels = None
depends_on = None

# Define the enum in Python
class AuditStatusEnum(str, enum.Enum):
    pending = "pending"
    passed = "passed"
    failed = "failed"
    escalated = "escalated"

def upgrade() -> None:
    # 1. Create Enum type explicitly
    audit_status_enum = postgresql.ENUM(
        "pending", "passed", "failed", "escalated",
        name="auditstatusenum"
    )
    audit_status_enum.create(op.get_bind(), checkfirst=True)

    # 2. Add new columns to compliance_statuses table
    op.add_column("compliance_statuses", sa.Column("audit_status", sa.Enum(AuditStatusEnum, name="auditstatusenum"), nullable=True, server_default="pending"))
    op.add_column("compliance_statuses", sa.Column("audit_remarks", sa.Text(), nullable=True))
    op.add_column("compliance_statuses", sa.Column("next_audit_due_date", sa.Date(), nullable=True))
    op.add_column("compliance_statuses", sa.Column("last_updated_by_user_id", sa.UUID(), nullable=True))
    op.add_column("compliance_statuses", sa.Column("is_flagged_noncompliant", sa.Boolean(), default=False))
    op.add_column("compliance_statuses", sa.Column("escalation_level", sa.String(length=50), nullable=True))
    op.add_column("compliance_statuses", sa.Column("auto_alert_enabled", sa.Boolean(), default=True))
    op.add_column("compliance_statuses", sa.Column("flags_needs_review", sa.Boolean(), default=False))
    op.add_column("compliance_statuses", sa.Column("is_visible_to_regulator", sa.Boolean(), default=False))
    op.add_column("compliance_statuses", sa.Column("fire_risk_certificate_url", sa.String(), nullable=True))
    op.add_column("compliance_statuses", sa.Column("data_protection_registration_url", sa.String(), nullable=True))
    op.add_column("compliance_statuses", sa.Column("environmental_permit_url", sa.String(), nullable=True))
    op.add_column("compliance_statuses", sa.Column("gdpr_certificate_url", sa.String(), nullable=True))
    op.add_column("compliance_statuses", sa.Column("waste_license_certificate_url", sa.String(), nullable=True))
    op.add_column("compliance_statuses", sa.Column("iso_27001_certificate_url", sa.String(), nullable=True))
    op.add_column("compliance_statuses", sa.Column("data_protection_registration_valid", sa.Boolean(), default=False))
    op.add_column("compliance_statuses", sa.Column("environmental_permit_valid", sa.Boolean(), default=False))
    op.add_column("compliance_statuses", sa.Column("transport_license_valid", sa.Boolean(), default=False))
    op.add_column("compliance_statuses", sa.Column("staff_training_records_uploaded", sa.Boolean(), default=False))
    op.add_column("compliance_statuses", sa.Column("sharps_policy_uploaded", sa.Boolean(), default=False))
    op.add_column("compliance_statuses", sa.Column("clinical_waste_policy_uploaded", sa.Boolean(), default=False))
    op.add_column("compliance_statuses", sa.Column("gdpr_policy_uploaded", sa.Boolean(), default=False))
    op.add_column("compliance_statuses", sa.Column("fire_risk_assessment_complete", sa.Boolean(), default=False))
    op.alter_column("compliance_statuses", "last_audit_date", type_=sa.Date())

    # 3. Create notifications table
    op.create_table(
        "notifications",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, default=uuid4),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("is_read", sa.Boolean(), default=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    # Drop notifications table
    op.drop_table("notifications")

    # Drop compliance_statuses columns
    op.drop_column("compliance_statuses", "audit_status")
    op.drop_column("compliance_statuses", "audit_remarks")
    op.drop_column("compliance_statuses", "next_audit_due_date")
    op.drop_column("compliance_statuses", "last_updated_by_user_id")
    op.drop_column("compliance_statuses", "is_flagged_noncompliant")
    op.drop_column("compliance_statuses", "escalation_level")
    op.drop_column("compliance_statuses", "auto_alert_enabled")
    op.drop_column("compliance_statuses", "flags_needs_review")
    op.drop_column("compliance_statuses", "is_visible_to_regulator")
    op.drop_column("compliance_statuses", "fire_risk_certificate_url")
    op.drop_column("compliance_statuses", "data_protection_registration_url")
    op.drop_column("compliance_statuses", "environmental_permit_url")
    op.drop_column("compliance_statuses", "gdpr_certificate_url")
    op.drop_column("compliance_statuses", "waste_license_certificate_url")
    op.drop_column("compliance_statuses", "iso_27001_certificate_url")
    op.drop_column("compliance_statuses", "data_protection_registration_valid")
    op.drop_column("compliance_statuses", "environmental_permit_valid")
    op.drop_column("compliance_statuses", "transport_license_valid")
    op.drop_column("compliance_statuses", "staff_training_records_uploaded")
    op.drop_column("compliance_statuses", "sharps_policy_uploaded")
    op.drop_column("compliance_statuses", "clinical_waste_policy_uploaded")
    op.drop_column("compliance_statuses", "gdpr_policy_uploaded")
    op.drop_column("compliance_statuses", "fire_risk_assessment_complete")

    # Restore datetime if needed
    op.alter_column("compliance_statuses", "last_audit_date", type_=sa.DateTime())

    # Drop enum type explicitly
    audit_status_enum = postgresql.ENUM(
        "pending", "passed", "failed", "escalated",
        name="auditstatusenum"
    )
    audit_status_enum.drop(op.get_bind(), checkfirst=True)