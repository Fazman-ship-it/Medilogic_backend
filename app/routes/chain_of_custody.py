from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from app import models, schemas, database
from app.dependencies import get_current_user
import os
from datetime import datetime
from app.utilites.logging import log_activity
from app.database import get_db
from app.models import CustodyEventType, User
from typing import List
from fastapi import Path
from fastapi.responses import StreamingResponse,FileResponse
import csv
import io
import matplotlib.pyplot as plt
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.platypus import Table, TableStyle
from reportlab.lib import colors
import plotly.graph_objs as go


router = APIRouter(prefix="/custody", tags=["Chain of Custody"])

@router.post("/", response_model=schemas.ChainOfCustodyOut)
def log_custody_event(
    event: schemas.ChainOfCustodyCreate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
    file: UploadFile = File(None)
):
    # Step 1: Validate trip and multi-tenancy
    trip = db.query(models.Trip).filter(models.Trip.id == event.trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    
    if trip.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="Unauthorized for this trip")

    # Step 2: Save optional photo
    attachment_url = None
    if file:
        folder = "static/custody_photos"
        os.makedirs(folder, exist_ok=True)
        file_path = os.path.join(folder, file.filename)
        with open(file_path, "wb") as f:
            f.write(file.file.read())
        attachment_url = file_path

    # Step 3: Create custody log
    custody_log = models.ChainOfCustody(
        trip_id=event.trip_id,
        driver_id=current_user.id,
        event_type=event.event_type,
        location=event.location,
        notes=event.notes,
        attachment_url=attachment_url,
        timestamp=datetime.utcnow()
    )
    db.add(custody_log)
    db.commit()
    db.refresh(custody_log)

    # Step 4: Log activity
    log_activity(
        db=db,
        user_id=current_user.id,
        trip_id=event.trip_id,
        organization_id=current_user.organization_id,
        action=f"Logged custody event: {event.event_type}",
        details=f"Custody logged for Trip #{event.trip_id} by {current_user.name}",
        timestamp=datetime.utcnow()
    )

    # Step 5: Return response
    return custody_log

@router.get("/{trip_id}", response_model=List[schemas.ChainOfCustodyOut])
def get_custody_events(
    trip_id: int = Path(..., description="Trip ID to fetch custody events for"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Fetch trip to verify access
    trip = db.query(models.Trip).filter(models.Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    # Role-based access control
    if current_user.role == "driver" and trip.driver_id != current_user.id:
        raise HTTPException(status_code=403, detail="You don't have access to this trip")
    
    if current_user.role == "client" and trip.client_name != current_user.name:
        raise HTTPException(status_code=403, detail="Unauthorized: This is not your trip")

    if trip.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="Unauthorized: Different organization")

    # Fetch and return custody events
    events = db.query(models.ChainOfCustody)\
        .filter(models.ChainOfCustody.trip_id == trip_id)\
        .order_by(models.ChainOfCustody.timestamp)\
        .all()

    return events



@router.get("/export/{trip_id}")
def export_custody_log(
    trip_id: int,
    format: str = "csv",  # Now supports "csv" and "pdf"
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Validate trip
    trip = db.query(models.Trip).filter(models.Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    # Role-based filtering
    if current_user.role == "driver" and trip.driver_id != current_user.id:
        raise HTTPException(status_code=403, detail="You don't have access to this trip")
    if current_user.role == "client" and trip.client_name != current_user.name:
        raise HTTPException(status_code=403, detail="Unauthorized trip access")
    if trip.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="Unauthorized organization")

    # Get custody events
    events = db.query(models.ChainOfCustody).filter_by(trip_id=trip_id).all()
    if not events:
        raise HTTPException(status_code=404, detail="No custody events found for this trip")

    # --- EXPORT TO CSV ---
    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Timestamp", "Event Type", "Location", "Driver", "Notes", "Attachment URL"])
        for event in events:
            driver = db.query(User).filter(User.id == event.driver_id).first()
            writer.writerow([
                event.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                event.event_type,
                event.location,
                driver.name if driver else "Unknown",
                event.notes,
                event.attachment_url or ""
            ])
        output.seek(0)
        return StreamingResponse(output, media_type="text/csv", headers={
            "Content-Disposition": f"attachment; filename=custody_trip_{trip_id}.csv"
        })

    # --- EXPORT TO PDF ---
    elif format == "pdf":
        # Create chart of event counts
        event_counts = {}
        for event in events:
            event_counts[event.event_type] = event_counts.get(event.event_type, 0) + 1

        # Create bar chart
        plt.figure(figsize=(6, 3))
        plt.bar(event_counts.keys(), event_counts.values(), color="skyblue")
        plt.title("Custody Event Frequency")
        plt.xlabel("Event Type")
        plt.ylabel("Count")
        chart_path = f"static/custody_chart_{trip_id}.png"
        os.makedirs("static", exist_ok=True)
        plt.tight_layout()
        plt.savefig(chart_path)
        plt.close()

        # Create PDF
        pdf_path = f"static/custody_log_{trip_id}.pdf"
        c = canvas.Canvas(pdf_path, pagesize=A4)
        width, height = A4

        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, height - 50, "Medilogic - Chain of Custody Report")

        c.setFont("Helvetica", 11)
        y = height - 90
        c.drawString(50, y, f"Trip ID: {trip_id}")
        y -= 15
        c.drawString(50, y, f"Client: {trip.client_name}")
        y -= 15
        c.drawString(50, y, f"Driver: {current_user.name}")
        y -= 15
        c.drawString(50, y, f"Total Events: {len(events)}")

        # Insert chart
        y -= 170
        c.drawImage(chart_path, 50, y, width=500, height=140)

        # Insert event table
        y -= 160
        table_data = [["Time", "Event Type", "Location", "Driver", "Notes"]]
        for e in events:
            driver = db.query(User).filter(User.id == e.driver_id).first()
            table_data.append([
                e.timestamp.strftime("%Y-%m-%d %H:%M"),
                e.event_type,
                e.location,
                driver.full_name if driver else "Unknown",
                e.notes or ""
            ])
        table = Table(table_data, colWidths=[80, 90, 120, 80, 140])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#dee2e6")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor("#212529")),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
        ]))
        table.wrapOn(c, width, height)
        table.drawOn(c, 50, max(y - len(events)*12, 60))

        c.save()

        return FileResponse(pdf_path, media_type="application/pdf", filename=f"custody_trip_{trip_id}.pdf")

    # Invalid format
    raise HTTPException(status_code=400, detail="Unsupported export format. Use ?format=csv or ?format=pdf")


@router.get("/analytics/{trip_id}")
def custody_chart_data(
    trip_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    trip = db.query(models.Trip).filter_by(id=trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    # Authorization
    if current_user.role == "driver" and trip.driver_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    if current_user.role == "client" and trip.client_name != current_user.name:
        raise HTTPException(status_code=403, detail="Access denied")
    if trip.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="Unauthorized")

    events = db.query(models.ChainOfCustody).filter_by(trip_id=trip_id).order_by(models.ChainOfCustody.timestamp).all()

    if not events:
        raise HTTPException(status_code=404, detail="No events found")

    # Prepare data for chart
    timestamps = [e.timestamp.strftime("%Y-%m-%d %H:%M") for e in events]
    event_types = [e.event_type for e in events]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=timestamps,
        y=event_types,
        mode="lines+markers",
        line=dict(shape="hv", color="blue"),
        name="Custody Events"
    ))
    fig.update_layout(
        title="Chain of Custody Timeline",
        xaxis_title="Timestamp",
        yaxis_title="Event Type",
        height=500
    )

    return fig.to_dict()


@router.get("/export/{trip_id}")
def export_custody_log(
    trip_id: int,
    format: str = "csv",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Fetch trip and organization
    trip = db.query(models.Trip).filter(models.Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    organization = db.query(models.Organization).filter(models.Organization.id == trip.organization_id).first()
    if not organization:
        raise HTTPException(status_code=404, detail="Trip's organization not found")

    # --- ACCESS CONTROL ---
    if current_user.role == "admin":
        if trip.organization_id != current_user.organization_id:
            raise HTTPException(status_code=403, detail="Unauthorized access to trip")

    elif current_user.role == "regulator":
        # Enforce regulator jurisdiction filters
        if current_user.country and organization.country != current_user.regulated_country:
            raise HTTPException(status_code=403, detail="Trip outside your country jurisdiction")
        if current_user.region and organization.region != current_user.regulated_region:
            raise HTTPException(status_code=403, detail="Trip outside your region jurisdiction")
        if current_user.state and organization.state != current_user.regulated_state:
            raise HTTPException(status_code=403, detail="Trip outside your state jurisdiction")

    else:
        # All other roles forbidden
        raise HTTPException(status_code=403, detail="You do not have permission to export this trip")

    # --- FETCH EVENTS ---
    events = db.query(models.ChainOfCustody).filter_by(trip_id=trip_id).all()
    if not events:
        raise HTTPException(status_code=404, detail="No custody events found for this trip")

    # --- EXPORT FORMAT: CSV ---
    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)

        # CSV headers
        writer.writerow([
            "Timestamp",
            "Event Type",
            "Location",
            "Driver",
            "Notes",
            "Attachment URL"
        ])

        # CSV rows
        for event in events:
            driver = db.query(User).filter(User.id == event.driver_id).first()
            writer.writerow([
                event.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                event.event_type,
                event.location,
                driver.full_name if driver else "Unknown",
                event.notes,
                event.attachment_url or ""
            ])

        output.seek(0)
        return StreamingResponse(output, media_type="text/csv", headers={
            "Content-Disposition": f"attachment; filename=custody_trip_{trip_id}.csv"
        })

    raise HTTPException(status_code=400, detail="Unsupported export format. Use ?format=csv")