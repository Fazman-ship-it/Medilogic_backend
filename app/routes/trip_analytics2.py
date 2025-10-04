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
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.units import inch

router = APIRouter(prefix="/trips", tags=["Trip Export"])

# --- CSV Export (Professional SaaS Version) ---
def export_to_csv(data: list, filters: dict = None, org_name: str = "") -> io.BytesIO:
    buffer = io.BytesIO()
    text_stream = io.TextIOWrapper(buffer, encoding="utf-8-sig", newline="")
    writer = csv.writer(text_stream)

    # --- Metadata Section ---
    title = f"{org_name} - Trip Export Report" if org_name else "Trip Export Report"
    writer.writerow([f"# {title}"])
    writer.writerow([f"# Generated on: {now_utc().strftime('%Y-%m-%d %H:%M:%S UTC')}"])

    if filters:
        for key, value in filters.items():
            if value:
                writer.writerow([f"# {key.replace('_', ' ').title()}: {value}"])

    writer.writerow([])  # Blank line before table

    # --- Table Section ---
    fieldnames = [
        "ID", "Driver ID", "Driver Name", "Delivery Type", "Scheduled Time",
        "Cost", "Client Name", "Pickup Location", "Dropoff Location",
        "Distance (km)", "Status", "Notes", "Created At"
    ]
    writer.writerow(fieldnames)

    for row in data:
        writer.writerow([
            row.get("ID", ""),
            row.get("Driver ID", ""),
            row.get("Driver Name", ""),
            row.get("Delivery Type", ""),
            row.get("Scheduled Time", ""),
            str(row.get("Cost (£)", "")).replace("£", ""),  # numeric only
            row.get("Client Name", ""),
            row.get("Pickup Location", ""),
            row.get("Dropoff Location", ""),
            row.get("Distance (km)", ""),
            row.get("Status", ""),
            row.get("Notes", ""),
            row.get("Created At", ""),
        ])

    text_stream.flush()
    text_stream.detach()
    buffer.seek(0)
    return buffer


# --- PDF Export (Professional SaaS Version) ---
def export_to_pdf(data: list, filters: dict = None, org_name: str = "") -> io.BytesIO:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=60,
        bottomMargin=40
    )

    elements = []
    styles = getSampleStyleSheet()

    # --- Custom Professional Styles ---
    styles.add(ParagraphStyle(name="Header", fontSize=16, leading=20, alignment=1, textColor=colors.HexColor("#003366")))
    styles.add(ParagraphStyle(name="Subtle", fontSize=10, leading=14, textColor=colors.grey))
    styles.add(ParagraphStyle(name="TableText", fontSize=9, leading=12))

    # --- Title & timestamp ---
    title_text = f"{org_name} - Trip Export Report" if org_name else "Trip Export Report"
    title = Paragraph(title_text, styles["Header"])
    timestamp = Paragraph(f"Generated on: {now_utc().strftime('%Y-%m-%d %H:%M:%S UTC')}", styles["Subtle"])

    elements.extend([title, timestamp, Spacer(1, 12)])

    # --- Filters Summary ---
    if filters:
        filter_header = Paragraph("<b>Applied Filters:</b>", styles["Normal"])
        elements.append(filter_header)
        for key, value in filters.items():
            if value:
                elements.append(Paragraph(f"{key.replace('_', ' ').title()}: {value}", styles["Normal"]))
        elements.append(Spacer(1, 12))

    # --- Handle Empty Data ---
    if not data:
        elements.append(Paragraph("No records found for the selected filters.", styles["Normal"]))
        doc.build(elements)
        buffer.seek(0)
        return buffer

    # --- Table Data ---
    headers = list(data[0].keys())
    table_data = [headers]

    for row in data:
        wrapped_row = [
            Paragraph(str(value), styles["TableText"]) if value else Paragraph("", styles["TableText"])
            for value in row.values()
        ]
        table_data.append(wrapped_row)

    table = Table(table_data, repeatRows=1, hAlign="LEFT")
    col_count = len(headers)
    table._argW = [doc.width / col_count] * col_count

    # --- Professional Styling ---
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#003366")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('ALIGN', (0,0), (-1,0), 'CENTER'),
        ('FONTSIZE', (0,0), (-1,0), 11),
        ('BOTTOMPADDING', (0,0), (-1,0), 8),
        ('TOPPADDING', (0,0), (-1,0), 8),
        ('GRID', (0,0), (-1,-1), 0.3, colors.HexColor("#CCCCCC")),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.whitesmoke, colors.lightgrey]),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 4),
        ('RIGHTPADDING', (0,0), (-1,-1), 4),
    ]))

    elements.append(table)

    # --- Footer ---
    def footer(canvas, doc):
        canvas.saveState()
        footer_text = f"© {now_utc().year} {org_name or 'Medilogic'} | Generated by Medilogic Platform"
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.grey)
        canvas.drawCentredString(letter[0]/2, 0.5 * inch, footer_text)
        canvas.restoreState()

    doc.build(elements, onFirstPage=footer, onLaterPages=footer)
    buffer.seek(0)
    return buffer


# --- Export Endpoint ---
@router.get("/export")
def export_trips(
    format: Literal["csv", "pdf"] = Query(..., description="Export format: csv or pdf"),
    start_date: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="End date YYYY-MM-DD"),
    client_name: Optional[str] = Query(None),
    delivery_type: Optional[str] = Query(None),
    driver_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin"))
):
    query = (
        db.query(models.Trip, models.User.name.label("driver_name"))
        .outerjoin(models.User, models.Trip.driver_id == models.User.id)
        .filter(models.Trip.organization_id == current_user.organization_id)
    )

    if start_date:
        try:
            query = query.filter(models.Trip.scheduled_time >= datetime.strptime(start_date, "%Y-%m-%d"))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_date format. Use YYYY-MM-DD.")
    if end_date:
        try:
            query = query.filter(models.Trip.scheduled_time <= datetime.strptime(end_date, "%Y-%m-%d"))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_date format. Use YYYY-MM-DD.")
    if client_name:
        query = query.filter(models.Trip.client_name.ilike(f"%{client_name}%"))
    if delivery_type:
        query = query.filter(models.Trip.delivery_type == delivery_type)
    if driver_id:
        query = query.filter(models.Trip.driver_id == driver_id)

    results = query.all()
    if not results:
        raise HTTPException(status_code=404, detail="No trips found")

    data = [{
        "ID": str(trip.id),
        "Driver ID": str(trip.driver_id) if trip.driver_id else "",
        "Driver Name": driver_name or "",
        "Delivery Type": trip.delivery_type or "",
        "Scheduled Time": trip.scheduled_time.strftime("%Y-%m-%d %H:%M:%S UTC") if trip.scheduled_time else "",
        "Cost (£)": f"{trip.cost:.2f}" if trip.cost is not None else "",
        "Client Name": trip.client_name or "",
        "Pickup Location": trip.pickup_location or "",
        "Dropoff Location": trip.dropoff_location or "",
        "Distance (km)": f"{trip.distance_km:.1f}" if trip.distance_km is not None else "",
        "Status": trip.status or "",
        "Notes": trip.notes or "",
        "Created At": trip.created_at.strftime("%Y-%m-%d %H:%M:%S UTC") if trip.created_at else "",
    } for trip, driver_name in results]

    filters = {
        "Start Date": start_date,
        "End Date": end_date,
        "Client Name": client_name,
        "Delivery Type": delivery_type,
        "Driver ID": driver_id,
    }

    org_name = current_user.organization.name if current_user.organization else "Organization"
    timestamp = now_utc().strftime("%Y%m%d_%H%M%S")
    filename = f"{org_name.replace(' ', '_').lower()}_trip_export_{timestamp}.{format}"

    if format == "csv":
        buffer = export_to_csv(data, filters, org_name)
        return StreamingResponse(
            buffer,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )

    if format == "pdf":
        buffer = export_to_pdf(data, filters, org_name)
        return StreamingResponse(
            buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )

