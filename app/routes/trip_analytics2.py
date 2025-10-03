from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional, Literal
from uuid import UUID
import csv
import io
import pandas as pd
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from app import models
from app.database import get_db
from app.dependencies import require_role
from app.utilites.time_utilities import now_utc

router = APIRouter(prefix="/trips", tags=["Trip Export"])

def export_to_csv(data: list, filters: dict = None) -> io.StringIO:
    buffer = io.StringIO()
    writer = csv.writer(buffer)

    # --- Metadata Section ---
    writer.writerow(["Trip Export Report"])
    writer.writerow([f"Generated on: {now_utc().strftime('%Y-%m-%d %H:%M:%S UTC')}"])

    if filters:
        for key, value in filters.items():
            if value:
                writer.writerow([f"{key.replace('_', ' ').title()}: {value}"])
    writer.writerow([])  # Blank line before table

    # --- Table Section ---
    fieldnames = [
        "ID", "Driver ID", "Delivery Type", "Scheduled Time",
        "Cost (£)", "Client Name", "Pickup Location", "Dropoff Location",
        "Distance (km)", "Status", "Notes", "Created At"
    ]
    writer.writerow(fieldnames)

    for row in data:
        writer.writerow([row[field] for field in fieldnames])

    buffer.seek(0)
    return buffer

# --- PDF Export ---
def export_to_pdf(data: list) -> io.BytesIO:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=letter, 
        rightMargin=20, 
        leftMargin=20, 
        topMargin=40, 
        bottomMargin=20
    )
    elements = []
    styles = getSampleStyleSheet()

    # Title & timestamp
    title = Paragraph("Trip Export Report", styles["Title"])
    timestamp = Paragraph(
        f"Generated on: {now_utc().strftime('%Y-%m-%d %H:%M:%S UTC')}", 
        styles["Normal"]
    )
    elements.extend([title, timestamp, Spacer(1, 20)])

    # Build table data (headers + rows)
    headers = list(data[0].keys())
    table_data = [headers]

    for row in data:
        # ✅ Convert each value to Paragraph (so it wraps instead of cutting)
        wrapped_row = [
            Paragraph(str(value), styles["Normal"]) if value else Paragraph("", styles["Normal"]) 
            for value in row.values()
        ]
        table_data.append(wrapped_row)

    # Create styled table
    table = Table(table_data, repeatRows=1, hAlign="LEFT")

    # ✅ Auto-fit columns by setting colWidths
    # - distribute width across page
    col_count = len(headers)
    table._argW = [doc.width / col_count] * col_count

    table.setStyle(TableStyle([
        # Header row
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#003366")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 10),
        ('ALIGN', (0,0), (-1,0), 'CENTER'),

        # Body rows
        ('FONTSIZE', (0,1), (-1,-1), 8),
        ('GRID', (0,0), (-1,-1), 0.25, colors.grey),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.whitesmoke, colors.lightgrey]),

        # Wrap text alignment
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))

    elements.append(table)
    doc.build(elements)
    buffer.seek(0)
    return buffer


@router.get("/export")
def export_trips(
    format: Literal["csv", "pdf"] = Query(..., description="Export format: csv or pdf"),
    start_date: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="End date YYYY-MM-DD"),
    client_name: Optional[str] = Query(None),
    delivery_type: Optional[str] = Query(None),
    driver_id: Optional[UUID] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin"))
):
    # --- Build Query ---
    query = db.query(models.Trip).filter(models.Trip.organization_id == current_user.organization_id)

    if start_date:
        try:
            query = query.filter(models.Trip.scheduled_time >= datetime.strptime(start_date, "%Y-%m-%d"))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid start_date format. Use YYYY-MM-DD.")

    if end_date:
        try:
            query = query.filter(models.Trip.scheduled_time <= datetime.strptime(end_date, "%Y-%m-%d"))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid end_date format. Use YYYY-MM-DD.")

    if client_name:
        query = query.filter(models.Trip.client_name.ilike(f"%{client_name}%"))
    if delivery_type:
        query = query.filter(models.Trip.delivery_type == delivery_type)
    if driver_id:
        query = query.filter(models.Trip.driver_id == driver_id)

    trips = query.all()
    if not trips:
        raise HTTPException(status_code=404, detail="No trips found")

    # --- Prepare Data ---
    data = [{
        "ID": str(trip.id),
        "Driver ID": str(trip.driver_id) if trip.driver_id else "",
        "Delivery Type": (
            trip.delivery_type if trip.delivery_type != "custom" 
            else trip.custom_delivery_description or "Custom"
        ),
        "Scheduled Time": trip.scheduled_time.strftime("%Y-%m-%d %H:%M") if trip.scheduled_time else "",
        "Cost (£)": f"{trip.cost:.2f}" if trip.cost is not None else "",
        "Client Name": trip.client_name or "", 
        "Pickup Location": trip.pickup_location or "",
        "Dropoff Location": trip.dropoff_location or "",
        "Distance (km)": f"{trip.distance_km:.1f}" if trip.distance_km is not None else "",
        "Status": trip.status or "",
        "Notes": trip.notes or "",
        "Created At": trip.created_at.strftime("%Y-%m-%d %H:%M") if trip.created_at else "",
    } for trip in trips]

    # --- Export ---
    if format == "csv":
        buffer = export_to_csv(data)
        return StreamingResponse(buffer, media_type="text/csv",
                                 headers={"Content-Disposition": "attachment; filename=trips.csv"})
    
    if format == "pdf":
        buffer = export_to_pdf(data)
        return StreamingResponse(buffer, media_type="application/pdf",
                                 headers={"Content-Disposition": "attachment; filename=trips.pdf"})