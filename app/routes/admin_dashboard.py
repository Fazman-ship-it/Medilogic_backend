from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional, List
from app.database import get_db
from app.dependencies import get_current_user
from app import models
from collections import Counter
import pandas as pd
import csv
import io
from fastapi.responses import StreamingResponse
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import os
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from app.models import PriorityLevel
import plotly.graph_objects as go
from app.utilites.generator import generate_invite_code
from app.dependencies import require_role
from app.utilites.logging import log_activity
from app import schemas
from app.models import ShiftAssignment,User
from datetime import date
from uuid import UUID

router = APIRouter(
    prefix="/admin-dashboard",
    tags=["Admin Dashboard"]
)

@router.get("/")
def get_admin_dashboard(
    start_date: Optional[datetime] = Query(None),
    priority: Optional[str] = Query(None),
    end_date: Optional[datetime] = Query(None),
    delivery_type: Optional[str] = Query(None),
    client_name: Optional[str] = Query(None),
    driver_name: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # ✅ Only admins can access
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can access this dashboard.")

    # ✅ Multi-tenant filter
    query = db.query(models.Trip).filter(models.Trip.organization_id == current_user.organization_id)

    # Filters
    if start_date and end_date:
        query = query.filter(models.Trip.scheduled_time.between(start_date, end_date))
    if priority:
        try:
            priority_enum = PriorityLevel(priority)  # convert string to Enum
            query = query.filter(models.Trip.priority == priority_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid priority level. Choose from: normal, urgent, stat.")
    if delivery_type:
        query = query.filter(models.Trip.delivery_type == delivery_type)
    if client_name:
        query = query.filter(models.Trip.client_name == client_name)
    if driver_name:
        query = query.filter(models.Trip.driver_name == driver_name)

    trips = query.all()

    # Summary stats
    total_trips = len(trips)
    completed = len([t for t in trips if t.status == "completed"])
    in_progress = len([t for t in trips if t.status == "in_progress"])
    cancelled = len([t for t in trips if t.status == "cancelled"])
    total_cost = sum(t.cost or 0 for t in trips)

    # Top drivers by completed trips
    driver_counts = Counter(t.driver_name for t in trips if t.driver_name)
    top_drivers = driver_counts.most_common(5)

    # Most active clients
    client_counts = Counter(t.client_name for t in trips if t.client_name)
    top_clients = client_counts.most_common(5)

    return {
        "filters": {
            "start_date": start_date,
            "end_date": end_date,
            "delivery_type": delivery_type,
            "client_name": client_name,
            "driver_name": driver_name
        },
        "summary": {
            "total_trips": total_trips,
            "completed": completed,
            "in_progress": in_progress,
            "cancelled": cancelled,
            "total_cost": total_cost
        },
        "top_drivers": [
            {"driver_name": name, "trip_count": count} for name, count in top_drivers
        ],
        "top_clients": [
            {"client_name": name, "trip_count": count} for name, count in top_clients
        ],
        "trips": trips  # optional: return full trip list
    }
    

@router.get("/export/csv")
def export_csv(
    status: Optional[str] = Query(None),
    delivery_type: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can export CSV reports.")

    # ✅ Multi-tenant: restrict to user's organization
    query = db.query(models.Trip).filter(models.Trip.organization_id == current_user.organization_id)

    if status:
        query = query.filter(models.Trip.status == status)
    if delivery_type:
        query = query.filter(models.Trip.delivery_type == delivery_type)
    if priority:
        try:
            priority_enum = PriorityLevel(priority)
            query = query.filter(models.Trip.priority == priority_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid priority level. Choose from: normal, urgent, stat.")
    if start_date and end_date:
        query = query.filter(models.Trip.scheduled_time.between(start_date, end_date))

    trips = query.all()

    output = io.StringIO()
    writer = csv.writer(output)

    # ✅ Write CSV Header
    writer.writerow([
        "Trip ID", "Driver ID", "Client Name", "Delivery Type",
        "Priority", "Status", "Cost", "Scheduled Time"
    ])

    # ✅ Write Trip Rows
    for t in trips:
        writer.writerow([
            t.id,
            t.driver_id,
            t.client_name,
            t.delivery_type,
            t.priority,
            t.status,
            f"£{t.cost:.2f}" if t.cost is not None else "N/A",
            t.scheduled_time.strftime("%Y-%m-%d %H:%M") if t.scheduled_time else "N/A"
        ])

    output.seek(0)
    return StreamingResponse(output, media_type="text/csv", headers={
        "Content-Disposition": "attachment; filename=trips_report.csv"
    })

@router.get("/charts")
def get_admin_dashboard_charts(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Access restricted to admins.")

    # ✅ Multi-tenant: filter by organization
    query = db.query(models.Trip).filter(models.Trip.organization_id == current_user.organization_id)

    if start_date and end_date:
        query = query.filter(models.Trip.scheduled_time.between(start_date, end_date))

    trips = query.all()

    # ============================
    # 📊 1. Trips per waste type
    # ============================
    delivery_counts = {}
    for trip in trips:
        delivery_counts[trip.delivery_type] = delivery_counts.get(trip.delivery_type, 0) + 1

    fig1 = go.Figure(data=[go.Pie(labels=list(delivery_counts.keys()), values=list(delivery_counts.values()))])
    fig1.update_layout(title="Trips by Delivery Type")

    # ============================
    # 📊 2. Monthly Trip Count
    # ============================
    monthly_counts = {}
    for trip in trips:
        if trip.scheduled_time:
            month_str = trip.scheduled_time.strftime("%Y-%m")
            monthly_counts[month_str] = monthly_counts.get(month_str, 0) + 1

    sorted_months = sorted(monthly_counts.keys())
    fig2 = go.Figure(data=[go.Bar(x=sorted_months, y=[monthly_counts[m] for m in sorted_months])])
    fig2.update_layout(title="Monthly Trip Volume", xaxis_title="Month", yaxis_title="Trips")

    # ============================
    # 📊 3. Top 5 Drivers by Trips
    # ============================
    driver_counts = {}
    for trip in trips:
        driver_id = trip.driver_id
        driver_counts[driver_id] = driver_counts.get(driver_id, 0) + 1

    sorted_drivers = sorted(driver_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    driver_ids = [str(d[0]) for d in sorted_drivers]
    trip_counts = [d[1] for d in sorted_drivers]

    fig3 = go.Figure(data=[go.Bar(x=driver_ids, y=trip_counts)])
    fig3.update_layout(title="Top 5 Drivers by Trips", xaxis_title="Driver ID", yaxis_title="Trips")

    # ============================
    # 📦 Return HTML components
    # ============================
    return {
        "delivery_type_chart": fig1.to_json(),
        "monthly_trips_chart": fig2.to_json(),
        "top_drivers_chart": fig3.to_json()
    }


@router.get("/export/pdf")
def export_admin_pdf_with_charts(
    status: Optional[str] = Query(None),
    delivery_type: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can export PDF reports.")

    # 🧠 Query Trips
    query = db.query(models.Trip).filter(models.Trip.organization_id == current_user.organization_id)
    if status:
        query = query.filter(models.Trip.status == status)
    if delivery_type:
        query = query.filter(models.Trip.delivery_type == delivery_type)
    if priority:
        query = query.filter(models.Trip.priority == priority)
    if start_date and end_date:
        query = query.filter(models.Trip.scheduled_time.between(start_date, end_date))

    trips = query.all()

    # 🖼 Prepare Plotly Charts
    def generate_chart_image(fig: go.Figure):
        image_bytes = fig.to_image(format="png", width=600, height=400)
        return ImageReader(io.BytesIO(image_bytes))

    # Chart 1: Monthly Trip Count
    monthly_counts = {}
    for t in trips:
        if t.scheduled_time:
            key = t.scheduled_time.strftime("%Y-%m")
            monthly_counts[key] = monthly_counts.get(key, 0) + 1
    months = sorted(monthly_counts)
    fig_months = go.Figure(data=[go.Bar(x=months, y=[monthly_counts[m] for m in months])])
    fig_months.update_layout(title="Monthly Trip Volume")
    chart1_img = generate_chart_image(fig_months)

    # Chart 2: Delivery Types
    delivery_counts = {}
    for t in trips:
        if t.delivery_type:
            delivery_counts[t.delivery_type] = delivery_counts.get(t.delivery_type, 0) + 1
    fig_delivery = go.Figure(data=[go.Pie(labels=list(delivery_counts.keys()), values=list(delivery_counts.values()))])
    fig_delivery.update_layout(title="Trips by Delivery Type")
    chart2_img = generate_chart_image(fig_delivery)

    # Chart 3: Top Drivers
    driver_counts = {}
    for t in trips:
        if t.driver_id:
            driver_counts[t.driver_id] = driver_counts.get(t.driver_id, 0) + 1
    top_drivers = sorted(driver_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    driver_ids = [str(d[0]) for d in top_drivers]
    driver_values = [d[1] for d in top_drivers]
    fig_drivers = go.Figure(data=[go.Bar(x=driver_ids, y=driver_values)])
    fig_drivers.update_layout(title="Top Drivers by Trips")
    chart3_img = generate_chart_image(fig_drivers)

    # 🧾 Generate PDF
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 50

    # ✅ Branding: Logo + Org Name
    logo_path = "app/static/logo.png"
    if os.path.exists(logo_path):
        p.drawImage(ImageReader(logo_path), 50, y - 40, width=80, height=40)
    org_name = getattr(current_user, "organization_name", "Organization")
    p.setFont("Helvetica-Bold", 16)
    p.drawString(150, y, f"{org_name} – Admin Trip Report")
    y -= 60

    # ✅ Trip Summary Table
    p.setFont("Helvetica", 9)
    for trip in trips[:15]:  # limit for space
        date_str = trip.scheduled_time.strftime("%d-%b-%Y %H:%M") if trip.scheduled_time else "N/A"
        p.drawString(
            50, y,
            f"Trip ID: {trip.id} | Client: {trip.client_name} | Delivery: {trip.delivery_type} | "
            f"Priority: {trip.priority} | Cost: £{trip.cost} | Date: {date_str}"
        )
        y -= 18
        if y < 100:
            p.showPage()
            y = height - 50

    # 🧠 Insert Charts
    for chart_img in [chart1_img, chart2_img, chart3_img]:
        p.showPage()
        p.drawImage(chart_img, 50, 300, width=500, height=300)

    p.save()
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=admin_trip_report.pdf"}
    )


@router.get("/assignments", summary="Admin: View shift assignments")
def get_shift_assignments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    driver_id: Optional[UUID] = Query(None),
    shift_date: Optional[date] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
):
    # ✅ Only admin or superadmin allowed
    if current_user.role not in ["admin", "superadmin"]:
        raise HTTPException(status_code=403, detail="Only admins can view shift assignments")

    query = db.query(ShiftAssignment)

    # ✅ Multi-tenant filter: Admins see only their org
    if current_user.role != "superadmin":
        query = query.filter(ShiftAssignment.organization_id == current_user.organization_id)

    # ✅ Filters
    if driver_id:
        query = query.filter(ShiftAssignment.driver_id == driver_id)

    if shift_date:
        query = query.filter(ShiftAssignment.shift_date == shift_date)

    if start_date and end_date:
        query = query.filter(ShiftAssignment.shift_date.between(start_date, end_date))

    query = query.order_by(ShiftAssignment.shift_date.asc(), ShiftAssignment.start_time.asc())

    assignments = query.all()

    results = []
    for a in assignments:
        driver = db.query(models.User).get(a.driver_id)
        results.append({
            "shift_id": a.id,
            "date": a.date,
            "start_time": a.start_time,
            "end_time": a.end_time,
            "driver_id": a.driver_id,
            "driver_name": driver.name if driver else None,
            "organization_id": a.organization_id
        })

    return results