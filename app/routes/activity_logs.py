from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime
import csv
import io
from fpdf import FPDF
from app.models import ActivityLog, User
from app.dependencies import get_db
from app.dependencies import get_current_user

router = APIRouter(
    prefix="/activity-logs",
    tags=["Audit Trail"]
)

@router.get("", summary="View activity logs", response_model=List[dict], description ="Admin and Super_admin can view activity logs of users in their organization.")
def get_activity_logs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    user_id: Optional[int] = Query(None),
    organization_id: Optional[int] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
):
    if current_user.role not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Access denied")

    query = db.query(ActivityLog)

    if current_user.role != "super_admin":
        query = query.filter(ActivityLog.organization_id == current_user.organization_id)

    if user_id:
        query = query.filter(ActivityLog.user_id == user_id)

    if organization_id:
        if current_user.role != "super_admin":
            raise HTTPException(status_code=403, detail="Only super_admin can filter by organization.")
        query = query.filter(ActivityLog.organization_id == organization_id)

    if start_date:
        query = query.filter(ActivityLog.timestamp >= start_date)

    if end_date:
        query = query.filter(ActivityLog.timestamp <= end_date)

    logs = query.order_by(ActivityLog.timestamp.desc()).all()

    return [
        {
            "id": log.id,
            "timestamp": log.timestamp,
            "user_id": log.user_id,
            "action": log.action,
            "details": log.details,
            "ip_address": log.ip_address,
            "user_agent": log.user_agent,
            "organization_id": log.organization_id
        }
        for log in logs
    ]

# ✅ Export logs as CSV
@router.get("/export/csv", summary="Export activity logs as CSV")
def export_logs_csv(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    user_id: Optional[int] = Query(None),
    organization_id: Optional[int] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
):
    if current_user.role not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Access denied")

    query = db.query(ActivityLog)

    if current_user.role != "super_admin":
        query = query.filter(ActivityLog.organization_id == current_user.organization_id)

    if user_id:
        query = query.filter(ActivityLog.user_id == user_id)
    if organization_id:
        if current_user.role != "super_admin":
            raise HTTPException(status_code=403, detail="Only super_admin can filter by organization.")
        query = query.filter(ActivityLog.organization_id == organization_id)
    if start_date:
        query = query.filter(ActivityLog.timestamp >= start_date)
    if end_date:
        query = query.filter(ActivityLog.timestamp <= end_date)

    logs = query.order_by(ActivityLog.timestamp.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Timestamp", "User ID", "Action", "Details", "IP", "User Agent", "Organization ID"])

    for log in logs:
        writer.writerow([
            log.id,
            log.timestamp,
            log.user_id,
            log.action,
            log.details,
            log.ip_address,
            log.user_agent,
            log.organization_id
        ])

    response = Response(content=output.getvalue(), media_type="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=activity_logs.csv"
    return response

# ✅ Export logs as PDF
@router.get("/export/pdf", summary="Export activity logs as PDF")
def export_logs_pdf(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    user_id: Optional[int] = Query(None),
    organization_id: Optional[int] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
):
    if current_user.role not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Access denied")

    query = db.query(ActivityLog)

    if current_user.role != "super_admin":
        query = query.filter(ActivityLog.organization_id == current_user.organization_id)

    if user_id:
        query = query.filter(ActivityLog.user_id == user_id)
    if organization_id:
        if current_user.role != "super_admin":
            raise HTTPException(status_code=403, detail="Only super_admin can filter by organization.")
        query = query.filter(ActivityLog.organization_id == organization_id)
    if start_date:
        query = query.filter(ActivityLog.timestamp >= start_date)
    if end_date:
        query = query.filter(ActivityLog.timestamp <= end_date)

    logs = query.order_by(ActivityLog.timestamp.desc()).all()

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=10)
    pdf.set_auto_page_break(auto=True, margin=15)

    pdf.cell(200, 10, txt="Medilogic Audit Logs", ln=True, align="C")
    pdf.ln(5)

    for log in logs:
        pdf.multi_cell(0, 6, txt=(
            f"Timestamp: {log.timestamp}\n"
            f"User ID: {log.user_id}\n"
            f"Action: {log.action}\n"
            f"Details: {log.details}\n"
            f"IP: {log.ip_address}\n"
            f"User Agent: {log.user_agent}\n"
            f"Org ID: {log.organization_id}\n"
            f"{'-'*40}"
        ))

    response = Response(content=pdf.output(dest='S').encode('latin-1'), media_type="application/pdf")
    response.headers["Content-Disposition"] = "attachment; filename=activity_logs.pdf"
    return response