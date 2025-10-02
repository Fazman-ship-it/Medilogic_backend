# app/utils/compliance_alerts.py
from datetime import datetime, timedelta
from typing import List
from app.models import ComplianceStatus  # adjust as needed
from app.utilites.time_utilities import now_utc
def generate_compliance_alerts(compliance: ComplianceStatus) -> List[str]:
    alerts = []
    today = now_utc()

    if not compliance.gdpr_policy_uploaded:
        alerts.append("GDPR policy not uploaded")

    if not compliance.has_waste_license:
        alerts.append("No valid waste license")

    if not compliance.staff_training_records_uploaded:
        alerts.append("Missing staff training records")

    if not compliance.transport_license_valid:
        alerts.append("No valid transport license")

    if compliance.next_audit_due_date and compliance.next_audit_due_date < today:
        alerts.append("Audit is overdue")

    elif compliance.next_audit_due_date and compliance.next_audit_due_date < today + timedelta(days=14):
        alerts.append("Audit due soon")

    if compliance.audit_status.name.lower() == "failed":
        alerts.append("Last audit failed")

    if compliance.audit_status.name.lower() == "escalated":
        alerts.append("Compliance escalation in progress")

    if compliance.is_flagged_noncompliant:
        alerts.append("Organization is flagged non-compliant")

    return alerts