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

router = APIRouter(prefix="/trips", tags=["Trip Export"])

@router.get("/export")
def export_trips(
    format: Literal["csv", "pdf", "excel"] = Query(..., description="Export format: csv, pdf, excel"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    client_name: Optional[str] = Query(None),
    delivery_type: Optional[str] = Query(None),
    driver_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_role("admin"))
):
    query = db.query(models.Trip)
    query = query.filter(models.Trip.organization_id == _.organization_id)  # ✅ Multi-tenant

    # Date filtering
    try:
        if start_date:
            start_date = datetime.strptime(start_date, "%Y-%m-%d")
            query = query.filter(models.Trip.scheduled_time >= start_date)
        if end_date:
            end_date = datetime.strptime(end_date, "%Y-%m-%d")
            query = query.filter(models.Trip.scheduled_time <= end_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

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

    # Define output fields
    data = [{
        "ID": trip.id,
        "Driver ID": trip.driver_id,
        "Delivery Type": trip.delivery_type,
        "Scheduled Time": trip.scheduled_time.strftime("%Y-%m-%d %H:%M:%S"),
        "Cost": trip.cost,
        "Client Name": trip.client_name,
        "Pickup Location": trip.pickup_location,
        "Dropoff Location": trip.dropoff_location,
        "Distance (km)": trip.distance_km,
        "Status": trip.status,
        "Created At": trip.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        "Location Zone": getattr(trip, "location_zone", "N/A"),
        "Vehicle Type": getattr(trip, "vehicle_type", "N/A"),
        "Shift Window": getattr(trip, "shift_window", "N/A"),
        "Compliance Flag": getattr(trip, "compliance_flag", False),
        "Created By": getattr(trip, "created_by", "System")
    } for trip in trips]

    # CSV export
    if format == "csv":
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)
        buffer.seek(0)
        return StreamingResponse(buffer, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=trips.csv"})

    # Excel export
    elif format == "excel":
        df = pd.DataFrame(data)
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Trips")
        buffer.seek(0)
        return StreamingResponse(buffer, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                 headers={"Content-Disposition": "attachment; filename=trips.xlsx"})

    # PDF export
    elif format == "pdf":
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter
        y = height - 40
        p.setFont("Helvetica", 10)
        p.drawString(40, y, "Exported Trip Report")
        y -= 20

        for i, trip in enumerate(data):
            for key, value in trip.items():
                p.drawString(40, y, f"{key}: {value}")
                y -= 15
                if y < 40:
                    p.showPage()
                    y = height - 40
            y -= 10

        p.save()
        buffer.seek(0)
        return StreamingResponse(buffer, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=trips.pdf"})

    # Fallback (should never happen)
    raise HTTPException(status_code=400, detail="Invalid export format")