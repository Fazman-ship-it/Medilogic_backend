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
from uuid import UUID

router = APIRouter(
    prefix="/activity-logs",
    tags=["Audit Trail"]
)

@router.get("", summary="View activity logs", response_model=List[dict], description ="Admin and Super_admin can view activity logs of users in their organization.")
def get_activity_logs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    user_id: Optional[UUID] = Query(None),
    organization_id: Optional[UUID] = Query(None),
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

# ✅ Export logs as CSV (Professional Format)
@router.get("/export/csv", summary="Export activity logs as CSV")
def export_logs_csv(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    user_id: Optional[UUID] = Query(None),
    organization_id: Optional[UUID] = Query(None),
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

    # ✅ Metadata row (report info)
    writer.writerow([f"Medilogic Audit Logs Export - Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"])
    writer.writerow([])  # blank line for readability

    # ✅ Column headers (professional naming)
    writer.writerow([
        "Log ID",
        "Timestamp (UTC)",
        "User ID",
        "Action",
        "Details",
        "IP Address",
        "User Agent",
        "Organization ID"
    ])

    # ✅ Data rows
    for log in logs:
        writer.writerow([
            str(log.id),
            log.timestamp.strftime("%Y-%m-%d %H:%M:%S") if log.timestamp else "",
            str(log.user_id) if log.user_id else "",
            log.action or "",
            log.details or "",
            log.ip_address or "",
            log.user_agent or "",
            str(log.organization_id) if log.organization_id else ""
        ])

    # ✅ Build response
    response = Response(content=output.getvalue(), media_type="text/csv")
    response.headers["Content-Disposition"] = f"attachment; filename=activity_logs_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return response

# ✅ Export logs as PDF (Professional Format)
@router.get("/export/pdf", summary="Export activity logs as PDF")
def export_logs_pdf(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    user_id: Optional[UUID] = Query(None),
    organization_id: Optional[UUID] = Query(None),
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

    # ✅ Setup PDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # ✅ Title
    pdf.set_font("Arial", "B", 14)
    pdf.cell(200, 10, "Medilogic Audit Logs", ln=True, align="C")

    # ✅ Report metadata
    pdf.set_font("Arial", "", 10)
    generated_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    pdf.cell(200, 8, f"Generated: {generated_time}", ln=True, align="R")

    # ✅ Filters summary
    filters_applied = []
    if user_id: filters_applied.append(f"User ID: {user_id}")
    if organization_id: filters_applied.append(f"Org ID: {organization_id}")
    if start_date: filters_applied.append(f"From: {start_date.strftime('%Y-%m-%d')}")
    if end_date: filters_applied.append(f"To: {end_date.strftime('%Y-%m-%d')}")
    if not filters_applied:
        filters_applied.append("No filters applied")

    pdf.multi_cell(0, 8, f"Filters: {', '.join(filters_applied)}")
    pdf.ln(5)

    # ✅ Table header
    pdf.set_font("Arial", "B", 9)
    col_widths = [40, 28, 25, 25, 25, 40]  # widths for each column
    headers = ["Timestamp", "User ID", "Action", "IP Address", "Org ID", "Details"]

    for i, header in enumerate(headers):
        pdf.cell(col_widths[i], 8, header, border=1, align="C")
    pdf.ln()

    # ✅ Table rows
    pdf.set_font("Arial", "", 8)
    for log in logs:
        row = [
            log.timestamp.strftime("%Y-%m-%d %H:%M") if log.timestamp else "",
            str(log.user_id)[:8] if log.user_id else "",  # shorten UUID
            log.action or "",
            log.ip_address or "",
            str(log.organization_id)[:8] if log.organization_id else "",
            (log.details[:30] + "...") if log.details and len(log.details) > 30 else (log.details or "")
        ]
        for i, value in enumerate(row):
            pdf.cell(col_widths[i], 8, value, border=1)
        pdf.ln()

    # ✅ Footer (page number)
    pdf.set_y(-15)
    pdf.set_font("Arial", "I", 8)
    pdf.cell(0, 10, f"Page {pdf.page_no()}", align="C")

    # ✅ Response
    response = Response(
        content=pdf.output(dest="S").encode("latin-1"),
        media_type="application/pdf"
    )
    response.headers["Content-Disposition"] = f"attachment; filename=activity_logs_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
    return response