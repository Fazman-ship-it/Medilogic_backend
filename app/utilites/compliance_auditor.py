from sqlalchemy.orm import Session
from datetime import datetime
from app.models import ComplianceStatus
from app.notifications import send_compliance_alert  # This triggers both email + app notifications

def run_compliance_audit_check(db: Session):
    """
    Runs compliance audit across all organizations.
    Flags overdue audits and sends alerts if auto_alert_enabled.
    """
    now = datetime.utcnow()

    # Get all compliance statuses where audit is overdue and alert is enabled
    overdue_statuses = db.query(ComplianceStatus).filter(
        ComplianceStatus.next_audit_due != None,
        ComplianceStatus.next_audit_due < now,
        ComplianceStatus.auto_alert_enabled == True,
        ComplianceStatus.is_flagged_non_compliant == False
    ).all()

    flagged = []

    for status in overdue_statuses:
        # Update compliance fields
        status.is_flagged_non_compliant = True
        status.audit_status = "non_compliant"
        status.flags = "Overdue audit"
        status.audit_remarks = "This record has passed its next audit due date."
        status.needs_review = True

        # Send alert (multi-tenant aware)
        send_compliance_alert(
            org_id=status.organization_id,
            reason="Overdue audit detected for one or more compliance records."
        )

        flagged.append(status)

    db.commit()
    return flagged