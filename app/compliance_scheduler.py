import io
import csv
from datetime import datetime
from sqlalchemy.orm import Session
from app.database import SessionLocal,get_db
from app.models import Organization, ComplianceStatus
from app.utilites.email_utilites import send_email  # Adjust path if needed

def generate_compliance_csv(orgs):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Organization",
        "ISO 27001 Certified",
        "NHS DSP Toolkit Complete",
        "Cyber Essentials Ready",
        "Waste License Present",
        "Last Audit Date"
    ])
    
    for org in orgs:
        comp = org.compliance_status
        writer.writerow([
            org.name,
            "Yes" if comp and comp.iso_27001_certified else "No",
            "Yes" if comp and comp.nhs_dsp_toolkit_complete else "No",
            "Yes" if comp and comp.cyber_essentials_ready else "No",
            "Yes" if comp and comp.has_waste_license else "No",
            comp.last_audit_date.strftime('%Y-%m-%d') if comp and comp.last_audit_date else "N/A"
        ])
    
    output.seek(0)
    return output.getvalue()

def send_weekly_compliance_reports():
    db: Session = SessionLocal()
    try:
        # Get all regulators (users with role='regulator')
        regulators = db.execute(
            "SELECT * FROM users WHERE role = 'regulator'"
        ).fetchall()
        
        for reg in regulators:
            # Filter orgs in their regulated jurisdiction
            orgs = db.query(Organization).filter(
                Organization.country == reg.regulated_country,
                Organization.state == reg.regulated_state,
                Organization.region == reg.regulated_region
            ).all()
            
            if orgs:
                csv_data = generate_compliance_csv(orgs)
                subject = "🧾 Weekly Compliance Report - Medilogic"
                body = f"Dear Regulator,\n\nPlease find attached the weekly compliance report for your jurisdiction.\n\nGenerated on {datetime.utcnow().strftime('%Y-%m-%d')}.\n\nRegards,\nMedilogic Compliance Engine"

                send_email(
                    to=reg.email,
                    subject=subject,
                    body=body,
                    attachments=[("compliance_report.csv", csv_data)]
                )
    finally:
        db.close()