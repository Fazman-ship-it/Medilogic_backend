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
from uuid import UUID
import uuid
from app.utilites.time_utilities import now_utc
router = APIRouter(prefix="/custody", tags=["Chain of Custody"])

# routes/chain_of_custody.py
import os
import io
from app.utilites.storage_utilites import (
    upload_file_to_s3_async,
    delete_file_from_s3,
    generate_presigned_url_async,
)
import json
from fastapi import Form

ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".pdf"}
MAX_FILE_SIZE_MB = 8
PRESIGNED_EXPIRES = 600  # seconds (10 minutes)


@router.post("/", response_model=schemas.ChainOfCustodyOut)
async def log_custody_event(
    event: str = Form(...),  # ✅ still accepts JSON as string
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
    files: List[UploadFile] = File(None),  # ✅ changed from single file to multiple
):
    # ✅ Parse the JSON string from the "event" field
    event_data = json.loads(event)
    event = schemas.ChainOfCustodyCreate(**event_data)

    # Step 1: Validate trip and multi-tenancy
    trip = db.query(models.Trip).filter(models.Trip.id == event.trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    if trip.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="Unauthorized for this trip")

    # Step 2: Prepare uploads
    attachment_urls = []
    s3_keys = []

    if files:
        for file in files:
            ext = os.path.splitext(file.filename)[-1].lower()
            if ext not in ALLOWED_EXTS:
                raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

            contents = await file.read()
            size_mb = len(contents) / (1024 * 1024)
            if size_mb > MAX_FILE_SIZE_MB:
                raise HTTPException(
                    status_code=400,
                    detail=f"File {file.filename} too large. Max size is {MAX_FILE_SIZE_MB} MB"
                )

            # Generate safe S3 key
            unique_filename = f"{uuid.uuid4()}{ext}"
            s3_key = f"custody_photos/{trip.organization_id}/{unique_filename}"
            s3_keys.append(s3_key)

            # Upload to S3
            await upload_file_to_s3_async(file, prefix=f"custody_photos/{trip.organization_id}")

            # Generate presigned URL
            url = await generate_presigned_url_async(s3_key, expires_in=PRESIGNED_EXPIRES)
            attachment_urls.append(url)

    # Step 3: Save to DB in a transaction
    try:
        custody_log = models.ChainOfCustody(
            trip_id=event.trip_id,
            driver_id=current_user.id,
            event_type=event.event_type,
            location=event.location,
            notes=event.notes,
            # ✅ store the list of S3 keys (comma-separated for simplicity)
            attachment_url=",".join(s3_keys) if s3_keys else None,
            timestamp=now_utc(),
            organization_id=current_user.organization_id,
        )
        db.add(custody_log)
        db.commit()
        db.refresh(custody_log)

    except Exception as exc:
        db.rollback()
        # ✅ Cleanup failed uploads
        for key in s3_keys:
            try:
                await delete_file_from_s3(key)
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=f"Failed to create custody log: {str(exc)}")

    # Step 4: Activity log
    log_activity(
        db=db,
        user_id=current_user.id,
        action=f"Logged custody event: {event.event_type}",
        details=f"Custody logged for Trip #{event.trip_id} by {current_user.name}",
        trip_id=event.trip_id,
    )

    # Step 5: Return response
    return schemas.ChainOfCustodyOut(
        id=custody_log.id,
        trip_id=custody_log.trip_id,
        driver_id=custody_log.driver_id,
        event_type=custody_log.event_type,
        location=custody_log.location,
        notes=custody_log.notes,
        attachment_urls=attachment_urls,  # ✅ now includes multiple URLs
        timestamp=custody_log.timestamp,
    )

@router.get("/{trip_id}", response_model=List[schemas.ChainOfCustodyOut])
async def get_custody_events(
    trip_id: UUID = Path(..., description="Trip ID to fetch custody events for"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Step 1: Verify trip exists
    trip = db.query(models.Trip).filter(models.Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    # Step 2: Role-based access control
    if current_user.role == "driver" and trip.driver_id != current_user.id:
        raise HTTPException(status_code=403, detail="Unauthorized: This trip does not belong to you")

    if current_user.role == "client" and trip.client_id != current_user.id:
        raise HTTPException(status_code=403, detail="Unauthorized: This trip does not belong to you")

    if current_user.role != "super_admin" and trip.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="Unauthorized: Trip belongs to a different organization")

    # Step 3: Fetch custody events
    events = (
        db.query(models.ChainOfCustody)
        .filter(models.ChainOfCustody.trip_id == trip_id)
        .order_by(models.ChainOfCustody.timestamp.asc())
        .all()
    )

    # Step 4: Convert to schema + presigned URLs
    response_events = []
    for e in events:
        urls = []
        if e.attachment_url:
            presigned_url = await generate_presigned_url_async(
                e.attachment_url,
                expires_in=PRESIGNED_EXPIRES
            )
            urls.append(presigned_url)
        event_out = schemas.ChainOfCustodyOut.from_orm(e)
        event_out.attachment_urls = urls
        response_events.append(event_out)

    # Step 5: Log read access
    log_activity(
        db=db,
        user_id=current_user.id,
        trip_id=trip.id,
        action="Viewed custody events",
        details=f"User {getattr(current_user, 'full_name', current_user.id)} retrieved custody events for trip {trip.id}"
    )

    return response_events

@router.get("/export/{trip_id}")
async def export_custody_log(
    trip_id: UUID,
    format: str = "csv",  # Supports "csv" and "pdf"
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Validate trip
    trip = db.query(models.Trip).filter(models.Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    # Role-based access
    if current_user.role == "driver" and trip.driver_id != current_user.id:
        raise HTTPException(status_code=403, detail="You don't have access to this trip")
    if current_user.role == "client" and trip.client_name != current_user.name:
        raise HTTPException(status_code=403, detail="Unauthorized trip access")
    if trip.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="Unauthorized organization")

    # Fetch custody events
    events = db.query(models.ChainOfCustody)\
        .filter(models.ChainOfCustody.trip_id == trip_id)\
        .order_by(models.ChainOfCustody.timestamp)\
        .all()
    if not events:
        raise HTTPException(status_code=404, detail="No custody events found for this trip")

    # --- EXPORT TO CSV ---
    if format.lower() == "csv":
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header row
        writer.writerow([
            "Timestamp", "Event Type", "Location", "Driver", "Notes", "Attachments"
        ])

        for event in events:
            driver = db.query(User).filter(User.id == event.driver_id).first()

            # ✅ Use async helper for presigned URLs
            attachment_url = (
                await generate_presigned_url_async(event.attachment_url)
                if event.attachment_url else ""
            )

            writer.writerow([
                event.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                event.event_type,
                event.location,
                driver.full_name if driver else "Unknown",
                event.notes or "",
                attachment_url
            ])

        output.seek(0)
        return StreamingResponse(
            output,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=custody_trip_{trip_id}.csv"}
        )

    # --- EXPORT TO PDF ---
    elif format.lower() == "pdf":
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.platypus import Table, TableStyle
        from reportlab.lib import colors

        # Generate chart of event counts
        event_counts = {}
        for e in events:
            event_counts[e.event_type] = event_counts.get(e.event_type, 0) + 1

        plt.figure(figsize=(6, 3))
        plt.bar(event_counts.keys(), event_counts.values(), color="#4e73df")
        plt.title("Custody Event Frequency", fontsize=12)
        plt.xlabel("Event Type", fontsize=10)
        plt.ylabel("Count", fontsize=10)
        plt.tight_layout()

        # Save chart to bytes
        chart_bytes = io.BytesIO()
        plt.savefig(chart_bytes, format="PNG")
        plt.close()
        chart_bytes.seek(0)

        # Create PDF
        pdf_bytes = io.BytesIO()
        c = canvas.Canvas(pdf_bytes, pagesize=A4)
        width, height = A4

        # Header
        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, height - 50, "Medilogic - Chain of Custody Report")
        c.setFont("Helvetica", 11)
        y = height - 80
        c.drawString(50, y, f"Trip ID: {trip_id}")
        y -= 15
        c.drawString(50, y, f"Client: {trip.client_name}")
        y -= 15
        c.drawString(50, y, f"Driver: {current_user.name}")
        y -= 15
        c.drawString(50, y, f"Total Events: {len(events)}")
        y -= 30

        # Draw chart
        from reportlab.lib.utils import ImageReader
        chart_image = ImageReader(chart_bytes)
        c.drawImage(chart_image, 50, y - 140, width=500, height=140)
        y -= 160

        # Table of events
        table_data = [["Timestamp", "Event Type", "Location", "Driver", "Notes", "Attachment URL"]]
        for e in events:
            driver = db.query(User).filter(User.id == e.driver_id).first()

            # ✅ Use async helper for presigned URLs
            attachment_url = (
                await generate_presigned_url_async(e.attachment_url)
                if e.attachment_url else ""
            )

            table_data.append([
                e.timestamp.strftime("%Y-%m-%d %H:%M"),
                e.event_type,
                e.location,
                driver.full_name if driver else "Unknown",
                e.notes or "",
                attachment_url
            ])

        table = Table(table_data, colWidths=[80, 70, 100, 80, 140, 120])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#dee2e6")),
            ('TEXTCOLOR', (0,0), (-1,0), colors.HexColor("#212529")),
            ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
            ('FONTSIZE', (0,0), (-1,-1), 8),
            ('GRID', (0,0), (-1,-1), 0.25, colors.grey),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ]))
        table.wrapOn(c, width, height)
        table.drawOn(c, 50, max(y - len(events)*12, 50))

        c.showPage()
        c.save()
        pdf_bytes.seek(0)

        return StreamingResponse(
            pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=custody_trip_{trip_id}.pdf"}
        )

    else:
        raise HTTPException(
            status_code=400,
            detail="Unsupported export format. Use ?format=csv or ?format=pdf"
        )



@router.get("/analytics/{trip_id}")
def custody_chart_data(
    trip_id: UUID,
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

    events = db.query(models.ChainOfCustody)\
        .filter_by(trip_id=trip_id)\
        .order_by(models.ChainOfCustody.timestamp).all()

    if not events:
        raise HTTPException(status_code=404, detail="No events found")

    # Prepare chart data
    timestamps = [e.timestamp for e in events]
    event_types = [e.event_type for e in events]
    drivers = [
        (db.query(models.User).filter_by(id=e.driver_id).first().full_name 
         if db.query(models.User).filter_by(id=e.driver_id).first() else "Unknown")
        for e in events
    ]
    severity_colors = {"low": "green", "moderate": "orange", "critical": "red"}
    colors = [severity_colors.get(e.severity.lower(), "blue") for e in events]

    # Plotly Scatter Timeline
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=timestamps,
        y=event_types,
        mode="markers",
        marker=dict(color=colors, size=12),
        text=[f"Driver: {d}<br>Notes: {e.notes or ''}" for d, e in zip(drivers, events)],
        hoverinfo="text+x+y",
        name="Custody Events"
    ))

    fig.update_layout(
        title=f"Chain of Custody Timeline - Trip {trip_id}",
        xaxis_title="Timestamp",
        yaxis_title="Event Type",
        height=500,
        template="plotly_white",
        hovermode="closest"
    )

    return fig.to_dict()

@router.get("/export_all/{trip_id}")
def export_custody_log(
    trip_id: UUID,
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

@router.get("/dashboard/admin/{organization_id}/custody-summary")
def admin_custody_summary(
    organization_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)  # ✅ match your code style
):
    # --- 1. Verify Admin Access ---
    if current_user.role != "admin" or current_user.organization_id != organization_id:
        raise HTTPException(status_code=403, detail="Unauthorized")

    # --- 2. Get Trips for Org ---
    trips = db.query(models.Trip).filter(models.Trip.organization_id == organization_id).all()
    total_trips = len(trips)
    if total_trips == 0:
        return {
            "organization_id": organization_id,
            "total_trips": 0,
            "trips_with_custody": 0,
            "compliance_rate": 0,
            "non_compliant_trips": [],
            "recent_events": []
        }

    # --- 3. Check Custody Compliance ---
    trips_with_custody = 0
    non_compliant_trips = []

    for trip in trips:
        events = db.query(models.ChainOfCustody).filter_by(trip_id=trip.id).all()
        if events:
            trips_with_custody += 1

            # Optional: Check for mandatory events
            event_types = [e.event_type.lower() for e in events]  # ✅ case-insensitive
            missing = []
            if "pickup" not in event_types:
                missing.append("pickup")
            if "delivery" not in event_types:
                missing.append("delivery")

            if missing:
                driver = db.query(User).filter_by(id=trip.driver_id).first()
                non_compliant_trips.append({
                    "trip_id": trip.id,
                    "client_name": trip.client_name,
                    "driver_name": driver.name if driver else "Unknown",
                    "missing_events": missing
                })
        else:
            # No custody events at all → non compliant
            driver = db.query(User).filter_by(id=trip.driver_id).first()
            non_compliant_trips.append({
                "trip_id": trip.id,
                "client_name": trip.client_name,
                "driver_name": driver.name if driver else "Unknown",
                "missing_events": ["pickup", "delivery"]
            })

    compliance_rate = (trips_with_custody / total_trips) * 100

    # --- 4. Get Recent Custody Events ---
    recent_events = db.query(models.ChainOfCustody)\
        .filter(models.ChainOfCustody.trip_id.in_([t.id for t in trips]))\
        .order_by(models.ChainOfCustody.timestamp.desc())\
        .limit(10).all()

    recent_event_list = [{
        "timestamp": e.timestamp,
        "event_type": e.event_type,
        "driver_name": db.query(User).filter_by(id=e.driver_id).first().name,
        "trip_id": e.trip_id
    } for e in recent_events]

    # --- 5. Return Dashboard Summary ---
    return {
        "organization_id": organization_id,
        "total_trips": total_trips,
        "trips_with_custody": trips_with_custody,
        "compliance_rate": round(compliance_rate, 2),
        "non_compliant_trips": non_compliant_trips,
        "recent_events": recent_event_list
    }