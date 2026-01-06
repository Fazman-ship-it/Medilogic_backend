# app/routes/confirm_receipt.py
from fastapi import APIRouter, Request, Depends, HTTPException, status, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from uuid import UUID
from datetime import datetime
import os, uuid, jwt,re
from app.database import get_db
from app.models import Trip, User
from app.dependencies import get_current_user
from app.config import settings
from app.crudy.delivery_confirmation import create_delivery_confirmation
from app.utilites.pdf_file_generator import generate_confirmation_pdf
from app.utilites.logging import log_activity
from app.utilites.storage_utilites import handle_file_upload
from app.crudy.delivery_confirmation import create_delivery_confirmation
from app.config import settings
import jwt
from app.utilites.token import generate_delivery_token

templates = Jinja2Templates(directory="app/templates")
router = APIRouter(tags=["Delivery Confirmation"])
SECRET_KEY = os.getenv("DELIVERY_CONFIRM_SECRET", "fallback_key")
ALGORITHM = "HS256"

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
        frontend_url = f"{settings.DELIVERY_CONFIRMATION_URL}{token}"
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
import io,re, csv
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
import time
import uuid
import base64
import csv
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Form, File, UploadFile, HTTPException, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
import os
from sqlalchemy.orm import Session
import jwt
import os

from app.models import Trip, DeliveryConfirmation, User
from app.dependencies import get_db, get_current_user_optional
from app.utilites.email_utilites import send_email
from app.utilites.logging import log_activity
from app.config import settings
from redis.asyncio import Redis
import logging
logger = logging.getLogger(__name__)
# --------------------------
# Rate limiting via Redis
# --------------------------
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = Redis.from_url(REDIS_URL, decode_responses=True)
_RATE_LIMIT_WINDOW_SECONDS = 60
_RATE_LIMIT_MAX_ATTEMPTS = 10

# File limits
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB

# --------------------------
# Unified delivery confirmation
# --------------------------
@router.post("/confirm", response_model=dict)
async def submit_delivery_confirmation(
    # Form inputs
    trip_id: Optional[UUID] = Form(None),  # Required for logged-in users
    token: Optional[str] = Form(None),    # Required for external users
    pin: Optional[str] = Form(None),
    external_client_name: Optional[str] = Form(None),
    external_client_email: Optional[str] = Form(None),
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
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Unified delivery confirmation endpoint for:
    - Internal/logged-in users (current_user)
    - External users (via token)
    """

    ip_address = request.client.host if request and request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")
        # --------------------------
    # Rate limiting with Redis
    # --------------------------
    try:
        redis_key = f"rate_limit:confirm:{ip_address}"

        count = await redis_client.get(redis_key)
        if count is None:
            await redis_client.set(redis_key, 1, ex=_RATE_LIMIT_WINDOW_SECONDS)
        else:
            count = int(count) + 1
            if count > _RATE_LIMIT_MAX_ATTEMPTS:
                raise HTTPException(status_code=429, detail="Too many requests from this IP")
            await redis_client.set(redis_key, count, ex=_RATE_LIMIT_WINDOW_SECONDS)

    except Exception:
        # Redis not available? Don't block confirmations
        pass

   
    # --------------------------
    # Identify user type & fetch trip
    # --------------------------
    if current_user:
        # Internal user
        if not trip_id:
            raise HTTPException(status_code=400, detail="trip_id is required for internal users")
        trip = db.query(Trip).filter(
            Trip.id == trip_id,
            Trip.organization_id == current_user.organization_id
        ).first()
        if not trip:
            raise HTTPException(status_code=404, detail="Trip not found or unauthorized")
        org_id = current_user.organization_id
    else:
        # External user
        if not token:
            raise HTTPException(status_code=400, detail="Token is required for external users")
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            trip_id_str = payload.get("trip_id")
            org_id_str = payload.get("organization_id")
            if not trip_id_str or not org_id_str:
                raise HTTPException(status_code=400, detail="Invalid token")
            trip_id = UUID(trip_id_str)
            org_id = UUID(org_id_str)
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token has expired")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid token")

        trip = db.query(Trip).filter(
            Trip.id == trip_id,
            Trip.organization_id == org_id
        ).first()
        if not trip:
            raise HTTPException(status_code=404, detail="Trip not found or unauthorized")

    # --------------------------
    # Duplicate confirmation
    # --------------------------
    existing_confirmation = db.query(DeliveryConfirmation).filter(
        DeliveryConfirmation.trip_id == trip.id
    ).first()
    if trip.is_delivered or (existing_confirmation and getattr(existing_confirmation, "is_confirmed", False)):
        raise HTTPException(status_code=409, detail="Trip already confirmed/delivered")

    # --------------------------
    # PIN validation
    # --------------------------
    pin_required = getattr(trip, "requires_pin", False) or getattr(trip, "pin_required", False)
    if pin_required:
        if not pin or len(pin.strip()) < 4:
            raise HTTPException(status_code=400, detail="PIN required and must be at least 4 characters")

    # --------------------------
    # Latitude / Longitude validation
    # --------------------------
    if latitude is not None and not (-90 <= latitude <= 90):
        raise HTTPException(status_code=400, detail="Invalid latitude")
    if longitude is not None and not (-180 <= longitude <= 180):
        raise HTTPException(status_code=400, detail="Invalid longitude")

    # --------------------------
    # File validation
    # --------------------------
    def _validate_upload_file(upload_file: UploadFile, field_name: str):
        if not upload_file:
            return
        content_type = upload_file.content_type or ""
        allowed = content_type.startswith("image/") or content_type == "application/pdf"
        if not allowed:
            raise HTTPException(status_code=400, detail=f"Invalid file type for {field_name}: {content_type}")
        try:
            cur = upload_file.file.tell()
            upload_file.file.seek(0, 2)
            size = upload_file.file.tell()
            upload_file.file.seek(cur)
            if size > _MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=400, detail=f"{field_name} too large (max 10MB)")
        except Exception:
            raise HTTPException(status_code=400, detail=f"Could not validate uploaded file size for {field_name}")

    uploaded_s3_keys = []
    confirmation = None

    try:
        file_mapping = {
            "signature_image_path": signature_image,
            "pickup_photo_path": pickup_photo,
            "disposal_facility_signature_path": facility_signature,
            "dropoff_photo_path": dropoff_photo
        }
        for fname, upf in file_mapping.items():
            if upf:
                _validate_upload_file(upf, fname)

        # --------------------------
        # Create delivery confirmation
        # --------------------------
        confirmation = create_delivery_confirmation(
            db=db,
            trip_id=trip.id,
            organization_id=org_id,
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

        # --------------------------
        # Upload files
        # --------------------------
        for field_name, upload_file in file_mapping.items():
            if upload_file:
                confirmation = await handle_file_upload(
                    app=confirmation,
                    file=upload_file,
                    prefix=f"{org_id}/delivery/{field_name}",
                    field_name=field_name,
                    db=db,
                    user_id=current_user.id if current_user else None,
                    action=f"upload_{field_name}"
                )
                uploaded_s3_keys.append(getattr(confirmation, field_name))

        # --------------------------
        # Generate PDF
        # --------------------------
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
            prefix=f"{org_id}/delivery/receipts",
            field_name="pdf_receipt_path",
            db=db,
            user_id=current_user.id if current_user else None,
            action="upload_pdf_receipt"
        )
        uploaded_s3_keys.append(getattr(confirmation, "pdf_receipt_path"))

        db.commit()
        db.refresh(confirmation)

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.exception("Error during delivery confirmation")
        from app.utilites.storage_utilites import delete_file_from_s3
        for key in uploaded_s3_keys:
            try:
                await delete_file_from_s3(key)
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=f"Delivery confirmation failed: {str(e)}")

    # --------------------------
    # Logging
    # --------------------------
    log_activity(
        db=db,
        user_id=current_user.id if current_user else None,
        action="delivery_confirmed",
        details=f"Trip {trip.id} confirmed | IP: {ip_address} | UA: {user_agent}"
    )

    # --------------------------
    # Generate presigned URLs
    # --------------------------
    presigned_urls = {}
    for field in ["pdf_receipt_path", "signature_image_path", "pickup_photo_path",
                  "disposal_facility_signature_path", "dropoff_photo_path"]:
        path = getattr(confirmation, field, None)
        if path:
            presigned_urls[field] = await generate_presigned_url_async(path)

    # --------------------------
    # CSV + PDF email for external client
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

    if confirmation.external_client_email:
        try:
            send_email(
                to_email=confirmation.external_client_email,
                subject=f"Trip {trip.id} Delivered - Medilogic",
                body="Your trip has been successfully delivered. Please find attached CSV and PDF.",
                attachments=attachments
        )
        except Exception:
            logger.exception("Email sending failed (non-blocking)")
        #  Don’t crash the confirmation if email fails
        pass

    return {
        "message": "Delivery confirmed",
        "presigned_urls": presigned_urls
    }