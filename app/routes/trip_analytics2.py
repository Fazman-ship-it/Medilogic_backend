from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional, Literal
import csv
import io
import pandas as pd
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from app import models
from app.database import get_db
from app.dependencies import require_role
from uuid import UUID 
from fastapi import APIRouter, Query, Depends, HTTPException
from fastapi.responses import StreamingResponse
from typing import Optional, Literal
from uuid import UUID
from datetime import datetime
import io
import csv
import pandas as pd
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.lib import colors
router = APIRouter(prefix="/trips", tags=["Trip Export"])

def export_to_csv(data: list) -> io.StringIO:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=data[0].keys())
    writer.writeheader()
    writer.writerows(data)
    buffer.seek(0)
    return buffer

def export_to_excel(data: list) -> io.BytesIO:
    df = pd.DataFrame(data)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Trips")
    buffer.seek(0)
    return buffer

def export_to_pdf(data: list) -> io.BytesIO:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []

    # Build table
    table_data = [list(data[0].keys())]  # headers
    for row in data:
        table_data.append(list(row.values()))

    table = Table(table_data, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#f2f2f2")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.black),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
    ]))

    elements.append(table)
    doc.build(elements)
    buffer.seek(0)
    return buffer

@router.get("/export")
def export_trips(
    format: Literal["csv", "excel", "pdf"] = Query(..., description="Export format: csv, excel, pdf"),
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

    # Date filter
    for date_str, field in [(start_date, "gte"), (end_date, "lte")]:
        if date_str:
            try:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                if field == "gte":
                    query = query.filter(models.Trip.scheduled_time >= date_obj)
                else:
                    query = query.filter(models.Trip.scheduled_time <= date_obj)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid date format: {date_str}. Use YYYY-MM-DD.")

    # Other filters
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
        "Driver ID": str(trip.driver_id),
        "Delivery Type": trip.delivery_type,
        "Scheduled Time": trip.scheduled_time.strftime("%Y-%m-%d %H:%M:%S"),
        "Cost": trip.cost,
        "Client Name": trip.client_name,
        "Pickup Location": trip.pickup_location,
        "Dropoff Location": trip.dropoff_location,
        "Distance (km)": trip.distance_km,
        "Status": trip.status,
        "Created At": trip.created_at.strftime("%Y-%m-%d %H:%M:%S")
    } for trip in trips]

    # --- Export ---
    if format == "csv":
        buffer = export_to_csv(data)
        return StreamingResponse(buffer, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=trips.csv"})
    
    if format == "excel":
        buffer = export_to_excel(data)
        return StreamingResponse(
            buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=trips.xlsx"}
        )

    if format == "pdf":
        buffer = export_to_pdf(data)
        return StreamingResponse(buffer, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=trips.pdf"})

    raise HTTPException(status_code=400, detail="Invalid export format")