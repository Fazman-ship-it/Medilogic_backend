# app/routes/confirm_receipt.py
from fastapi import APIRouter, Request, Depends, HTTPException, status, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from uuid import UUID
from datetime import datetime
import os, uuid, jwt
from app.database import get_db
from app.models import Trip, User
from app.dependencies import get_current_user
from app.config import settings
from app.crudy.delivery_confirmation import create_delivery_confirmation
from app.utilites.pdf_file_generator import generate_confirmation_pdf
from app.utilites.logging import log_activity

import uuid
from fastapi import APIRouter, Form, File, UploadFile, Request, Depends, HTTPException, status
from fastapi.responses import RedirectResponse, HTMLResponse
from app.dependencies import get_current_user
from app.models import Trip, User
from sqlalchemy.orm import Session
from app.database import get_db
from app.utilites.storage_utilites import handle_file_upload
from app.crudy.delivery_confirmation import create_delivery_confirmation
from app.config import settings
import jwt

templates = Jinja2Templates(directory="app/templates")
router = APIRouter(tags=["Delivery Confirmation"])
SECRET_KEY = os.getenv("DELIVERY_CONFIRM_SECRET", "fallback_key")
ALGORITHM = "HS256"

# app/routes/confirm_qr.py
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from uuid import UUID
import jwt
import os

from app.database import get_db
from app.models import Trip
from app.config import settings
from app.utilites.token import generate_delivery_token

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from uuid import UUID
import jwt, re
from app.database import get_db
from app.models import Trip, DeliveryConfirmation
from app.config import settings

# Simple email validation regex
EMAIL_REGEX = re.compile(r"^[^@]+@[^@]+\.[^@]+$")

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from uuid import UUID
import jwt
from app.database import get_db
from app.models import Trip
from app.config import settings

@router.get("/pickup-form", response_class=RedirectResponse)
def get_pickup_confirmation_form(token: str, db: Session = Depends(get_db)):
    """
    Redirects external users (via QR code) to the pickup confirmation page.
    Only validates token and trip existence.
    External client info will be entered in the form.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        trip_id_str = payload.get("trip_id")
        org_id_str = payload.get("organization_id")

        if not trip_id_str or not org_id_str:
            raise HTTPException(status_code=400, detail="Invalid token payload")

        # Convert to UUIDs
        try:
            trip_id = UUID(trip_id_str)
            org_id = UUID(org_id_str)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid UUID in token")

        # Fetch trip
        trip = db.query(Trip).filter(
            Trip.id == trip_id,
            Trip.organization_id == org_id
        ).first()

        if not trip:
            raise HTTPException(status_code=404, detail="Trip not found or unauthorized")

        # Check if pickup already exists
        from app.models import DeliveryConfirmation
        existing_confirmation = db.query(DeliveryConfirmation).filter(
            DeliveryConfirmation.trip_id == trip.id
        ).first()

        if existing_confirmation and existing_confirmation.pickup_photo_path:
            raise HTTPException(status_code=400, detail="Pickup already confirmed")

        # Redirect to frontend pickup confirmation page
        frontend_url = f"{settings.DELIVERY_CONFIRMATION_URL}?token={token}"
        return RedirectResponse(url=frontend_url, status_code=302)

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    
# === STEP 2: Show HTML Form (Optional if using SPA) ===
from fastapi import APIRouter, UploadFile, Form, File, Depends, Request, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID
from app.database import get_db
from app.models import Trip, User
from app.schemas import DeliveryConfirmationResponse
from app.dependencies import get_current_user
from app.utilites.logging import log_activity
from app.utilites.storage_utilites import handle_file_upload, generate_presigned_url_async, upload_file_to_s3_async
import uuid
import io

# app/routes/confirm_receipt.py
from fastapi import APIRouter, Request, Depends, Form, File, UploadFile, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID
from datetime import datetime
import io, csv, uuid, re
from app.database import get_db
from app.models import Trip, User, DeliveryConfirmation
from app.dependencies import get_current_user
from app.utilites.storage_utilites import handle_file_upload, generate_presigned_url_async
from app.utilites.pdf_file_generator import generate_confirmation_pdf
from app.utilites.logging import log_activity
from app.utilites.email_utilites import send_email
from app.crudy.delivery_confirmation import create_delivery_confirmation
from app.utilites.time_utilities import now_utc

EMAIL_REGEX = re.compile(r"^[^@]+@[^@]+\.[^@]+$")

def validate_email(email: str):
    if not email or not EMAIL_REGEX.match(email.strip()):
        raise HTTPException(status_code=400, detail=f"Invalid email: {email}")
    return email.strip()


import io
import csv
import uuid
import time
import base64
from typing import Optional
from datetime import datetime, timedelta

# Module-level simple in-memory rate limiter (for production: use Redis)
_RATE_LIMIT_WINDOW_SECONDS = 60
_RATE_LIMIT_MAX_ATTEMPTS = 10
_rate_limit_store: dict = {}  # ip -> {"count": int, "first_ts": float}

# File limits
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


@router.post("/confirm", response_model=dict)
async def submit_delivery_confirmation(
    trip_id: UUID = Form(...),
    pin: Optional[str] = Form(None),  # now optional
    external_client_name: str = Form(...),
    external_client_email: str = Form(...),
    wtn_code: str = Form(None),
    latitude: float = Form(None),
    longitude: float = Form(None),
    signature_image: UploadFile = File(None),
    pickup_photo: UploadFile = File(None),
    facility_signature: UploadFile = File(None),
    dropoff_photo: UploadFile = File(None),
    extra_notes: str = Form(None),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    ip_address = request.client.host if request and request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")

    # --------------------------
    # Rate limiting (simple)
    # --------------------------
    now_ts = time.time()
    rl = _rate_limit_store.get(ip_address)
    if rl is None or now_ts - rl["first_ts"] > _RATE_LIMIT_WINDOW_SECONDS:
        # reset window
        _rate_limit_store[ip_address] = {"count": 1, "first_ts": now_ts}
    else:
        rl["count"] += 1
        if rl["count"] > _RATE_LIMIT_MAX_ATTEMPTS:
            # too many attempts
            raise HTTPException(status_code=429, detail="Too many requests from this IP. Try again later.")

    # Validate email
    external_client_email = validate_email(external_client_email)

    # -----------------------------------
    # 🚧 MULTITENANT TRIP CHECK (strict)
    # -----------------------------------
    trip = db.query(Trip).filter(
        Trip.id == trip_id,
        Trip.organization_id == current_user.organization_id
    ).first()

    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found or unauthorized")

    # Duplicate confirmation / already delivered
    existing_confirmation = db.query(DeliveryConfirmation).filter(
        DeliveryConfirmation.trip_id == trip.id
    ).first()

    if trip.is_delivered or (existing_confirmation and getattr(existing_confirmation, "is_confirmed", False)):
        raise HTTPException(status_code=409, detail="Trip already confirmed/delivered")

    # If trip (or org) requires PIN then validate; otherwise PIN optional
    pin_required = bool(getattr(trip, "requires_pin", False) or getattr(trip, "pin_required", False))
    if pin_required:
        if not pin or len(pin.strip()) < 4:
            raise HTTPException(status_code=400, detail="PIN required and must be at least 4 characters")
    else:
        # if provided, do some light validation
        if pin and len(pin.strip()) > 0 and len(pin.strip()) < 4:
            raise HTTPException(status_code=400, detail="PIN too short")

    # Validate lat/lon
    if latitude is not None and not (-90 <= latitude <= 90):
        raise HTTPException(status_code=400, detail="Invalid latitude")
    if longitude is not None and not (-180 <= longitude <= 180):
        raise HTTPException(status_code=400, detail="Invalid longitude")

    # File validator helper
    def _validate_upload_file(upload_file: UploadFile, field_name: str):
        if not upload_file:
            return
        # MIME check
        content_type = upload_file.content_type or ""
        allowed = content_type.startswith("image/") or content_type == "application/pdf"
        if not allowed:
            raise HTTPException(status_code=400, detail=f"Invalid file type for {field_name}: {content_type}")

        # Size check (seek to end)
        try:
            cur = upload_file.file.tell()
            upload_file.file.seek(0, 2)  # seek to end
            size = upload_file.file.tell()
            upload_file.file.seek(cur)
            if size > _MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=400, detail=f"{field_name} too large (max 10MB)")
        except Exception:
            # If detection fails, be conservative and reject
            raise HTTPException(status_code=400, detail=f"Could not validate uploaded file size for {field_name}")

    uploaded_s3_keys = []
    confirmation = None

    try:
        # Validate files before uploading
        file_mapping = {
            "signature_image_path": signature_image,
            "pickup_photo_path": pickup_photo,
            "disposal_facility_signature_path": facility_signature,
            "dropoff_photo_path": dropoff_photo
        }
        for fname, upf in file_mapping.items():
            if upf:
                _validate_upload_file(upf, fname)

        # -----------------------------------
        # Create delivery confirmation (multi-tenant safe)
        # -----------------------------------
        confirmation = create_delivery_confirmation(
            db=db,
            trip_id=trip_id,
            organization_id=current_user.organization_id,  # enforce org
            pin_entered=pin,
            external_client_name=external_client_name,
            external_client_email=external_client_email,
            wtn_code=wtn_code,
            ip_address=ip_address,
            user_agent=user_agent,
            latitude=latitude,
            longitude=longitude,
            extra_notes=extra_notes,
            pickup_at=now_utc(),
            dropoff_at=now_utc()
        )

        # Upload files (namespaced by org)
        for field_name, upload_file in file_mapping.items():
            if upload_file:
                confirmation = await handle_file_upload(
                    app=confirmation,
                    file=upload_file,
                    prefix=f"{current_user.organization_id}/delivery/{field_name}",
                    field_name=field_name,
                    db=db,
                    user_id=current_user.id,
                    action=f"upload_{field_name}"
                )
                uploaded_s3_keys.append(getattr(confirmation, field_name))

        # --- Generate PDF receipt and upload ---
        pdf_bytes = generate_confirmation_pdf(confirmation)

        class BytesUploadFile:
            def __init__(self, content: bytes):
                self.file = io.BytesIO(content)
                self.filename = f"trip_receipt_{uuid.uuid4().hex}.pdf"
                self.content_type = "application/pdf"

        pdf_file = BytesUploadFile(pdf_bytes)
        confirmation = await handle_file_upload(
            app=confirmation,
            file=pdf_file,
            prefix=f"{current_user.organization_id}/delivery/receipts",
            field_name="pdf_receipt_path",
            db=db,
            user_id=current_user.id,
            action="upload_pdf_receipt"
        )
        uploaded_s3_keys.append(getattr(confirmation, "pdf_receipt_path"))

        # Mark trip delivered if your domain requires it here (create_delivery_confirmation might already do this)
        # trip.is_delivered = True
        # db.add(trip)

        db.commit()

    except HTTPException:
        # let HTTPExceptions bubble out unchanged
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        # cleanup any uploaded files
        from app.utilites.storage_utilites import delete_file_from_s3
        for key in uploaded_s3_keys:
            try:
                await delete_file_from_s3(key)
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=f"Delivery confirmation failed: {str(e)}")

    # Log activity
    log_activity(
        db=db,
        user_id=current_user.id,
        action="delivery_confirmed",
        details=f"Trip {trip_id} confirmed | IP: {ip_address} | UA: {user_agent}"
    )

    # Generate presigned URLs
    presigned_urls = {}
    for field in ["pdf_receipt_path", "signature_image_path", "pickup_photo_path",
                  "disposal_facility_signature_path", "dropoff_photo_path"]:
        path = getattr(confirmation, field, None)
        if path:
            presigned_urls[field] = await generate_presigned_url_async(path)

    # --------------------------
    # EMAIL ATTACHMENT CREATION (proper base64 encoding)
    # --------------------------
    csv_buffer = io.StringIO()
    csv_writer = csv.writer(csv_buffer)

    csv_writer.writerow([
        "Trip ID", "Client Name", "Client Email", "Driver Name",
        "External Client Signature", "Pickup Photo",
        "Disposal Facility Name", "Disposal Facility Address",
        "Facility Signature", "Dropoff Photo", "WTN Code",
        "Extra Notes", "Pickup Timestamp", "Dropoff Timestamp"
    ])

    csv_writer.writerow([
        str(trip.id),
        confirmation.external_client_name,
        confirmation.external_client_email,
        trip.driver_name,
        getattr(confirmation, "signature_image_path"),
        getattr(confirmation, "pickup_photo_path"),
        confirmation.disposal_facility_name,
        confirmation.disposal_facility_address,
        getattr(confirmation, "disposal_facility_signature_path"),
        getattr(confirmation, "dropoff_photo_path"),
        confirmation.wtn_code,
        confirmation.extra_notes,
        confirmation.pickup_at,
        confirmation.dropoff_at
    ])
    csv_bytes = csv_buffer.getvalue().encode("utf-8")

    attachments = [
        {
            "ContentType": "text/csv",
            "Filename": f"trip_{trip.id}_confirmation.csv",
            "Base64Content": base64.b64encode(csv_bytes).decode("utf-8")
        },
        {
            "ContentType": "application/pdf",
            "Filename": f"trip_{trip.id}_receipt.pdf",
            "Base64Content": base64.b64encode(pdf_bytes).decode("utf-8")
        }
    ]

    # Send email to external client if present
    if confirmation.external_client_email:
        send_email(
            to_email=confirmation.external_client_email,
            subject=f"Trip {trip.id} Delivered - Medilogic",
            body="Your trip has been successfully delivered. Please find attached CSV and PDF.",
            attachments=attachments
        )

    return {
        "message": "Delivery confirmed",
        "presigned_urls": presigned_urls
    }