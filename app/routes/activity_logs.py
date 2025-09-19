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

# ✅ View Logs
@router.get("", summary="View activity logs", response_model=List[dict], description="Admin and Super_admin can view activity logs of users in their organization.")
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


# ✅ Consistent CSV Export
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

    query = db.query(ActivityLog, User.name).join(User, User.id == ActivityLog.user_id)

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

    # ✅ Metadata
    writer.writerow([f"# Medilogic Audit Logs Export - Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"])

    # ✅ Core headers (consistent with PDF)
    writer.writerow([
        "Timestamp (UTC)",
        "User Name",
        "User ID",
        "Action",
        "Details",
        "IP Address",
        "Organization ID",
        "Log ID"
    ])

    # ✅ Data rows
    for log, full_name in logs:
        writer.writerow([
            log.timestamp.strftime("%Y-%m-%d %H:%M:%S") if log.timestamp else "",
            full_name or "",
            str(log.user_id) if log.user_id else "",
            log.action or "",
            log.details or "",
            log.ip_address or "",
            str(log.organization_id) if log.organization_id else "",
            str(log.id),
        ])

    response = Response(content=output.getvalue(), media_type="text/csv")
    response.headers["Content-Disposition"] = f"attachment; filename=activity_logs_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return response


# ✅ Consistent PDF Export
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

    query = db.query(ActivityLog, User.name).join(User, User.id == ActivityLog.user_id)

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

    # ✅ Metadata
    pdf.set_font("Arial", "", 10)
    generated_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    pdf.cell(200, 8, f"Generated: {generated_time}", ln=True, align="R")

    # ✅ Summary
    pdf.set_font("Arial", "B", 10)
    pdf.cell(0, 10, f"Total Logs: {len(logs)}", ln=True)
    failed = sum(1 for log, _ in logs if "failed" in (log.details or "").lower())
    pdf.cell(0, 8, f"Failed Logins: {failed}", ln=True)
    pdf.ln(3)

    # ✅ Table headers (aligned with CSV)
    pdf.set_font("Arial", "B", 8)
    headers = ["Timestamp", "User", "User ID", "Action", "Details", "IP", "Org ID", "Log ID"]
    col_widths = [25, 25, 30, 20, 50, 20, 25, 25]

    for i, header in enumerate(headers):
        pdf.cell(col_widths[i], 8, header, border=1, align="C")
    pdf.ln()

    # ✅ Table rows
    pdf.set_font("Arial", "", 7)
    for log, name in logs:
        row = [
            log.timestamp.strftime("%Y-%m-%d %H:%M") if log.timestamp else "",
            name or "",
            str(log.user_id) if log.user_id else "",
            log.action or "",
            log.details or "",
            log.ip_address or "",
            str(log.organization_id) if log.organization_id else "",
            str(log.id),
        ]
        for i, value in enumerate(row):
            if i == 4:  # Wrap details column
                pdf.multi_cell(col_widths[i], 8, value, border=1)
                pdf.ln()
            else:
                pdf.cell(col_widths[i], 8, value, border=1)
        pdf.ln()

    # ✅ Footer
    pdf.set_y(-15)
    pdf.set_font("Arial", "I", 8)
    pdf.cell(0, 10, f"Page {pdf.page_no()}", align="C")

    response = Response(
        content=pdf.output(dest="S").encode("latin-1"),
        media_type="application/pdf"
    )
    response.headers["Content-Disposition"] =(f"attachment; filename=activity_logs_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf")
    return response

from typing import Optional, Dict
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime
from app.models import ActivityLog, User
from app.dependencies import get_db, get_current_user
from app.schemas import ActivityLogAnalytics, ActivityLogSummary  # ✅ make sure these exist


# ✅ Analytics endpoint (now fully aligned with CSV/PDF filters)
@router.get(
    "/analytics",
    summary="Get activity log analytics",
    response_model=ActivityLogAnalytics
)
def get_activity_log_analytics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    user_id: Optional[UUID] = Query(None),
    organization_id: Optional[UUID] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
):
    if current_user.role not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Access denied")

    query = db.query(ActivityLog).join(User, User.id == ActivityLog.user_id)

    # ✅ Role restriction
    if current_user.role != "super_admin":
        query = query.filter(ActivityLog.organization_id == current_user.organization_id)

    # ✅ Apply filters (same as CSV/PDF)
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

    logs = query.all()

    # --- Compute Analytics ---
    total_logs = len(logs)
    failed_logins = sum(1 for log in logs if "failed" in (log.details or "").lower())
    actions_count: Dict[str, int] = {}
    activity_by_role: Dict[str, int] = {}
    activity_over_time: Dict[str, int] = {}
    user_activity: Dict[str, int] = {}

    for log in logs:
        # Count actions
        actions_count[log.action] = actions_count.get(log.action, 0) + 1

        # Count by role
        if log.user and log.user.role:
            activity_by_role[log.user.role] = activity_by_role.get(log.user.role, 0) + 1

        # Count by day
        day = log.timestamp.strftime("%Y-%m-%d") if log.timestamp else "Unknown"
        activity_over_time[day] = activity_over_time.get(day, 0) + 1

        # Track user activity
        if log.user and log.user.name:
            user_activity[log.user.name] = user_activity.get(log.user.name, 0) + 1

    # --- Extra Insights ---
    most_active_user = max(user_activity, key=user_activity.get) if user_activity else None
    most_common_action = max(actions_count, key=actions_count.get) if actions_count else None

    return ActivityLogAnalytics(
        summary=ActivityLogSummary(
            total_logs=total_logs,
            failed_logins=failed_logins,
            most_active_user=most_active_user,
            most_common_action=most_common_action,
        ),
        actions_count=actions_count,
        activity_by_role=activity_by_role,
        activity_over_time=activity_over_time,
    )