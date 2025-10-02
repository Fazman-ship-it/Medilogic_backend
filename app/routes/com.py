from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime, date
from fastapi.responses import StreamingResponse
from app.dependencies import get_db, get_current_user
from app.models import ComplianceStatus, User
from app.schemas import ComplianceScoreOut
from app.models import UserRole
import plotly.graph_objs as go
import csv
import io
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from io import BytesIO
from app.utilites.time_utilities import now_utc

router = APIRouter(prefix="/compliance-analytics", tags=["Compliance Analytics"])


@router.get("/", response_model=List[ComplianceScoreOut])
def get_compliance_analytics(
    export: Optional[str] = Query(None, description="csv or pdf"),
    chart: Optional[bool] = Query(False),
    risk_level: Optional[str] = Query(None, description="low, medium, high"),
    organization_name: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 🛡 Role-based filtering
    query = db.query(ComplianceStatus).join(User, ComplianceStatus.organization_id == User.organization_id)

    if current_user.role == UserRole.super_admin:
        pass
    elif current_user.role == UserRole.admin:
        query = query.filter(ComplianceStatus.organization_id == current_user.organization_id)
    elif current_user.role == UserRole.regulator:
        query = query.filter(
            User.regulated_country == current_user.regulated_country,
            User.regulated_state == current_user.regulated_state,
            User.regulated_region == current_user.regulated_region
        )
    else:
        raise HTTPException(status_code=403, detail="Not authorized")

    # 🔍 Additional filters
    if region:
        query = query.filter(User.regulated_region.ilike(f"%{region}%"))
    if organization_name:
        query = query.filter(User.organization_name.ilike(f"%{organization_name}%"))
    if start_date:
        query = query.filter(ComplianceStatus.created_at >= start_date)
    if end_date:
        query = query.filter(ComplianceStatus.created_at <= end_date)

    records = query.all()
    analytics = []

    for record in records:
        total_fields = 12
        passed = sum([
            record.iso_27001_certified,
            record.nhs_dsp_toolkit_complete,
            record.cyber_essentials_ready,
            record.has_waste_license,
            record.fire_risk_assessment_complete,
            record.gdpr_policy_uploaded,
            record.clinical_waste_policy_uploaded,
            record.sharps_policy_uploaded,
            record.staff_training_records_uploaded,
            record.transport_license_valid,
            record.environmental_permit_valid,
            record.data_protection_registration_valid,
        ])

        score = round((passed / total_fields) * 100, 2)
        is_compliant = score >= 80
        flagged = not is_compliant or record.audit_status.value in ["failed", "escalated"]

        # 🚦 AI-based risk level
        if score >= 90:
            risk = "low"
        elif score >= 70:
            risk = "medium"
        else:
            risk = "high"

        # 📢 Smart alert
        alert_message = None
        if not is_compliant:
            alert_message = "Organization is non-compliant"
        elif record.next_audit_due_date and record.next_audit_due_date < now_utc().date():
            alert_message = "Audit overdue"

        org_user = db.query(User).filter(User.organization_id == record.organization_id).first()

        analytics.append(ComplianceScoreOut(
            organization_id=record.organization_id,
            organization_name=org_user.organization_name if org_user else None,
            compliance_score=score,
            is_compliant=is_compliant,
            flagged=flagged,
            next_audit_due_date=record.next_audit_due_date,
            audit_status=record.audit_status.value,
            last_audit_date=record.last_audit_date,
            escalation_level=record.escalation_level,
            risk_level=risk,
            alert=alert_message
        ))

    # Filter by risk level after score computation
    if risk_level:
        analytics = [a for a in analytics if a.risk_level == risk_level]

    # 📊 Plotly Chart Output
    if chart:
        fig = go.Figure([
            go.Bar(
                x=[a.organization_name or str(a.organization_id) for a in analytics],
                y=[a.compliance_score for a in analytics],
                name="Compliance Score"
            )
        ])
        fig.update_layout(title="Compliance Scores by Organization", xaxis_title="Organization", yaxis_title="Score")
        return {"chart": fig.to_dict()}

    # 📤 CSV Export
    if export == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "organization_name", "organization_id", "compliance_score", "is_compliant",
            "flagged", "audit_status", "risk_level"
        ])
        for a in analytics:
            writer.writerow([
                a.organization_name, a.organization_id, a.compliance_score,
                a.is_compliant, a.flagged, a.audit_status, a.risk_level
            ])
        output.seek(0)
        return StreamingResponse(output, media_type="text/csv", headers={
            "Content-Disposition": "attachment; filename=compliance_analytics.csv"
        })

    # 📄 PDF Export
    if export == "pdf":
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        elements = [Paragraph("Compliance Analytics Report", styles['Heading1']), Spacer(1, 12)]

        data = [["Org Name", "Org ID", "Score", "Compliant", "Flagged", "Audit", "Risk"]]
        for a in analytics:
            data.append([
                a.organization_name, a.organization_id, a.compliance_score,
                "✅" if a.is_compliant else "❌",
                "🚩" if a.flagged else "",
                a.audit_status, a.risk_level
            ])

        table = Table(data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
        ]))
        elements.append(table)
        doc.build(elements)

        buffer.seek(0)
        return StreamingResponse(buffer, media_type="application/pdf", headers={
            "Content-Disposition": "attachment; filename=compliance_analytics.pdf"
        })

    return analytics