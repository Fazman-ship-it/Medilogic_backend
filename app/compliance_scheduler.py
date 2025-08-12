import io
import csv
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.database import SessionLocal
from app.models import Organization, ComplianceStatus
from app.utilites.email_utilites import send_email  # Adjust path if needed


def generate_compliance_csv(orgs):
    """
    Generate CSV data for compliance status of organizations.
    """
    output = io.StringIO()
    writer = csv.writer(output)

    # Updated header to reflect your new ComplianceStatus table fields
    writer.writerow([
        "Organization",
        "ISO 27001 Certified",
        "NHS DSP Toolkit Complete",
        "Cyber Essentials Ready",
        "Waste License Present",
        "Fire Risk Assessment Complete",
        "GDPR Policy Uploaded",
        "Clinical Waste Policy Uploaded",
        "Sharps Policy Uploaded",
        "Staff Training Records Uploaded",
        "Transport License Valid",
        "Environmental Permit Valid",
        "Data Protection Registration Valid",
        "Last Audit Date",
        "Next Audit Due Date",
        "Audit Status",
        "Audit Remarks",
        "Is Flagged Noncompliant",
        "Escalation Level",
        "Auto Alerts Enabled",
        "Needs Review Flag",
        "Visible to Regulator"
    ])

    for org in orgs:
        comp: ComplianceStatus = org.compliance_status
        writer.writerow([
            org.name,
            "Yes" if comp and comp.iso_27001_certified else "No",
            "Yes" if comp and comp.nhs_dsp_toolkit_complete else "No",
            "Yes" if comp and comp.cyber_essentials_ready else "No",
            "Yes" if comp and comp.has_waste_license else "No",
            "Yes" if comp and comp.fire_risk_assessment_complete else "No",
            "Yes" if comp and comp.gdpr_policy_uploaded else "No",
            "Yes" if comp and comp.clinical_waste_policy_uploaded else "No",
            "Yes" if comp and comp.sharps_policy_uploaded else "No",
            "Yes" if comp and comp.staff_training_records_uploaded else "No",
            "Yes" if comp and comp.transport_license_valid else "No",
            "Yes" if comp and comp.environmental_permit_valid else "No",
            "Yes" if comp and comp.data_protection_registration_valid else "No",
            comp.last_audit_date.strftime('%Y-%m-%d') if comp and comp.last_audit_date else "N/A",
            comp.next_audit_due_date.strftime('%Y-%m-%d') if comp and comp.next_audit_due_date else "N/A",
            comp.audit_status.value if comp and comp.audit_status else "N/A",
            comp.audit_remarks if comp and comp.audit_remarks else "",
            "Yes" if comp and comp.is_flagged_noncompliant else "No",
            comp.escalation_level if comp and comp.escalation_level else "none",
            "Yes" if comp and comp.auto_alert_enabled else "No",
            "Yes" if comp and comp.flags_needs_review else "No",
            "Yes" if comp and comp.is_visible_to_regulator else "No"
        ])

    output.seek(0)
    return output.getvalue()


def send_weekly_compliance_reports():
    """
    Send weekly compliance CSV reports to all regulators based on their jurisdiction.
    """
    db: Session = SessionLocal()
    try:
        # Fetch regulators using ORM to avoid raw SQL mismatch
        regulators = db.execute(
            text("SELECT * FROM users WHERE role = 'regulator'")
        ).mappings().all()

        for reg in regulators:
            # Ensure regulator has jurisdiction fields
            regulated_country = reg.get("regulated_country")
            regulated_state = reg.get("regulated_state")
            regulated_region = reg.get("regulated_region")

            if not (regulated_country and regulated_state and regulated_region):
                continue

            # Filter organizations in their jurisdiction
            orgs = db.query(Organization).filter(
                Organization.country == regulated_country,
                Organization.state == regulated_state,
                Organization.region == regulated_region
            ).all()
            if orgs:
                csv_data = generate_compliance_csv(orgs)
                subject = "🧾 Weekly Compliance Report - Medilogic"
                body = (
                    f"Dear Regulator,\n\n"
                    f"Please find attached the weekly compliance report for your jurisdiction.\n\n"
                    f"Generated on {datetime.utcnow().strftime('%Y-%m-%d')}.\n\n"
                    f"Regards,\nMedilogic Compliance Engine"
                )

                send_email(
                    to=reg.get("email"),
                    subject=subject,
                    body=body,
                    attachments=[("compliance_report.csv", csv_data)]
                )
    finally:
        db.close()