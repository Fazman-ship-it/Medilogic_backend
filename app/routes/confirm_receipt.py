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
from app.utilites.storage_utilites import handle_file_upload, generate_presigned_url_async, upload_file_to_s3_async,delete_file_from_s3
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

# Logging (Render-friendly)
# --------------------------
logger = logging.getLogger("confirm_receipt")
logger.setLevel(logging.INFO)

# --------------------------
# JWT settings
# --------------------------
SECRET_KEY = os.getenv("DELIVERY_CONFIRM_SECRET", "fallback_key")
ALGORITHM = "HS256"

# --------------------------
# Rate limiting via Redis
# --------------------------
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = Redis.from_url(REDIS_URL, decode_responses=True)

_RATE_LIMIT_WINDOW_SECONDS = 60
_RATE_LIMIT_MAX_ATTEMPTS = 10

# File limits
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB

from jwt import ExpiredSignatureError, InvalidTokenError

@router.post("/confirm", response_model=dict)
async def submit_delivery_confirmation(
    trip_id: Optional[UUID] = Form(None),
    token: Optional[str] = Form(None),
    pin: Optional[str] = Form(None),

    # client fields (auto-filled if trip has a client and these are empty)
    external_client_name: Optional[str] = Form(None),
    external_client_email: Optional[str] = Form(None),

    # WTN (auto-filled from trip.wtn_serial if admin already set it)
    wtn_code: Optional[str] = Form(None),

    latitude: Optional[float] = Form(None),
    longitude: Optional[float] = Form(None),

    signature_image: UploadFile = File(None),
    pickup_photo: UploadFile = File(None),

    disposal_facility_name: Optional[str] = Form(None),
    disposal_facility_address: Optional[str] = Form(None),

    facility_signature: UploadFile = File(None),
    dropoff_photo: UploadFile = File(None),
    extra_notes: Optional[str] = Form(None),

    request: Request = None,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    ip_address = request.client.host if request and request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")

    logger.info(f"[CONFIRM] Start | ip={ip_address} user={'yes' if current_user else 'no'}")
    print(f"[CONFIRM] Start | ip={ip_address} user={'yes' if current_user else 'no'}")

    # --------------------------
    # Rate limiting (non-blocking)
    # --------------------------
    try:
        redis_key = f"rate_limit:confirm:{ip_address}"
        count = await redis_client.get(redis_key)

        logger.info(f"[CONFIRM] Redis check | key={redis_key} count={count}")
        print(f"[CONFIRM] Redis check | key={redis_key} count={count}")

        if count is None:
            await redis_client.set(redis_key, 1, ex=_RATE_LIMIT_WINDOW_SECONDS)
        else:
            count = int(count) + 1
            if count > _RATE_LIMIT_MAX_ATTEMPTS:
                logger.warning(f"[CONFIRM] Rate limit exceeded | ip={ip_address}")
                raise HTTPException(status_code=429, detail="Too many requests from this IP")
            await redis_client.set(redis_key, count, ex=_RATE_LIMIT_WINDOW_SECONDS)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[CONFIRM] Redis failed (ignored): {e}")
        print("[CONFIRM] Redis failed (ignored):", repr(e))

    # --------------------------
    # Identify user type & fetch trip
    # --------------------------
    try:
        if current_user:
            if not trip_id:
                raise HTTPException(status_code=400, detail="trip_id is required for internal users")

            org_id = current_user.organization_id
            trip = db.query(Trip).filter(
                Trip.id == trip_id,
                Trip.organization_id == org_id
            ).first()

        else:
            if not token:
                raise HTTPException(status_code=400, detail="Token is required for external users")

            try:
                payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            except ExpiredSignatureError:
                logger.warning("[CONFIRM] Token expired")
                raise HTTPException(
                    status_code=401,
                    detail="Token has expired. Please request a new confirmation link."
                )
            except InvalidTokenError:
                logger.warning("[CONFIRM] Invalid token")
                raise HTTPException(
                    status_code=401,
                    detail="Invalid token. Please request a new confirmation link."
                )

            trip_id_str = payload.get("trip_id")
            org_id_str = payload.get("organization_id")

            if not trip_id_str or not org_id_str:
                raise HTTPException(status_code=400, detail="Invalid token payload")

            trip_id = UUID(trip_id_str)
            org_id = UUID(org_id_str)

            trip = db.query(Trip).filter(
                Trip.id == trip_id,Trip.organization_id == org_id
            ).first()

        if not trip:
            raise HTTPException(status_code=404, detail="Trip not found or unauthorized")

        logger.info(f"[CONFIRM] Trip fetched | trip_id={trip.id} org_id={org_id}")
        print(f"[CONFIRM] Trip fetched | trip_id={trip.id} org_id={org_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[CONFIRM] Trip lookup failed: {e}")
        print("[CONFIRM] Trip lookup failed:", repr(e))
        raise HTTPException(status_code=500, detail="Internal error while fetching trip")

    # --------------------------
    # ✅ AUTO-FILL CLIENT NAME/EMAIL (if trip has client)
    # --------------------------
    try:
        client_user = None
        if getattr(trip, "client_id", None):
            client_user = db.query(User).filter(User.id == trip.client_id).first()

        # Only fill if frontend didn’t send anything
        if not external_client_name:
            external_client_name = (
                getattr(client_user, "name", None)
                or getattr(trip, "client_name", None)
                or None
            )

        if not external_client_email:
            external_client_email = (
                getattr(client_user, "email", None)
                or getattr(trip, "client_email", None)  # only if you have this field
                or None
            )
    except Exception as e:
        logger.exception(f"[CONFIRM] Auto-fill client failed (ignored): {e}")
        print("[CONFIRM] Auto-fill client failed (ignored):", repr(e))

    # --------------------------
    # ✅ AUTO-FILL WTN FROM TRIP
    # --------------------------
    trip_requires_wtn = bool(getattr(trip, "requires_wtn", False))
    trip_wtn_serial = getattr(trip, "wtn_serial", None)

    # Final WTN: prefer form value, else trip value
    final_wtn_code = (wtn_code or trip_wtn_serial or None)

    # Enforce WTN if required
    if trip_requires_wtn and not final_wtn_code:
        raise HTTPException(status_code=400, detail="WTN code is required for this trip")

    # --------------------------
    # Duplicate confirmation check
    # --------------------------
    try:
        existing_confirmation = db.query(DeliveryConfirmation).filter(
            DeliveryConfirmation.trip_id == trip.id
        ).first()

        if getattr(trip, "is_delivered", False) or (
            existing_confirmation and getattr(existing_confirmation, "is_confirmed", False)
        ):
            raise HTTPException(status_code=409, detail="Trip already confirmed/delivered")

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[CONFIRM] Duplicate check failed: {e}")
        print("[CONFIRM] Duplicate check failed:", repr(e))
        raise HTTPException(status_code=500, detail="Internal error during duplicate check")

    # --------------------------
    # PIN validation (presence only here; strict match happens in create_delivery_confirmation)
    # --------------------------
    try:
        pin_required = bool(getattr(trip, "requires_pin", False) or getattr(trip, "pin_required", False))
        if pin_required:
            expected_len = 6  # must match generate_delivery_pin()
            if not pin:
                raise HTTPException(status_code=400, detail="PIN is required")

            pin_clean = pin.strip()
            if len(pin_clean) != expected_len or not pin_clean.isdigit():
                raise HTTPException(
                    status_code=400,
                    detail=f"PIN must be exactly {expected_len} digits"
                )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[CONFIRM] PIN validation failed: {e}")
        print("[CONFIRM] PIN validation failed:", repr(e))
        raise HTTPException(status_code=500, detail="Internal error during PIN validation")

    # --------------------------
    # File validation helper
    # --------------------------
    def _validate_upload_file(upload_file: UploadFile, field_name: str):
        if not upload_file:
            return
        content_type = upload_file.content_type or ""
        allowed = content_type.startswith("image/") or content_type == "application/pdf"
        if not allowed:
            raise HTTPException(status_code=400, detail=f"Invalid file type for {field_name}: {content_type}")

        cur = upload_file.file.tell()
        upload_file.file.seek(0, 2)
        size = upload_file.file.tell()
        upload_file.file.seek(cur)

        if size > _MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=400, detail=f"{field_name} too large (max 10MB)")

    uploaded_s3_keys = []
    confirmation = None
    pdf_bytes = None

    # --------------------------
    # Main confirm flow
    # --------------------------
    try:
        file_mapping = {
            "signature_image": signature_image,
            "pickup_photo": pickup_photo,
            "disposal_facility_signature": facility_signature,
            "dropoff_photo": dropoff_photo,
        }

        for fname, upf in file_mapping.items():
            if upf:
                _validate_upload_file(upf, fname)

        logger.info("[CONFIRM] File validation passed")
        print("[CONFIRM] File validation passed")

        confirmation = create_delivery_confirmation(
            db=db,
            trip_id=trip.id,
            organization_id=org_id,
            pin_entered=pin,
            external_client_name=external_client_name,
            external_client_email=external_client_email,

            # ✅ use final_wtn_code (auto-filled)
            wtn_code=final_wtn_code,

            ip_address=ip_address,
            user_agent=user_agent,
            latitude=latitude,
            longitude=longitude,
            extra_notes=extra_notes,
            pickup_at=now_utc(),
            dropoff_at=now_utc(),

            disposal_facility_name=disposal_facility_name,
            disposal_facility_address=disposal_facility_address,
        )

        logger.info(f"[CONFIRM] Confirmation created (pre-upload) | id={confirmation.id}")
        print(f"[CONFIRM] Confirmation created (pre-upload) | id={confirmation.id}")

        # Upload files
        for field_name, upload_file in file_mapping.items():
            if upload_file:
                logger.info(f"[CONFIRM] Uploading file | field={field_name}")
                print(f"[CONFIRM] Uploading file | field={field_name}")

                confirmation = await handle_file_upload(
                    app=confirmation,
                    file=upload_file,
                    prefix=f"{org_id}/delivery/{field_name}",
                    field_name=field_name,
                    db=db,
                    user_id=current_user.id if current_user else None,
                    action=f"upload_{field_name}",
                )

                uploaded_s3_keys.append(getattr(confirmation, f"{field_name}_path", None))

        logger.info("[CONFIRM] File uploads done")
        print("[CONFIRM] File uploads done")

        # Generate PDF
        try:
            logger.info("[CONFIRM] Generating PDF...")
            print("[CONFIRM] Generating PDF...")
            pdf_bytes = generate_confirmation_pdf(confirmation)
        except Exception as e:
            logger.exception(f"[CONFIRM] PDF generation failed: {e}")
            print("[CONFIRM] PDF generation failed:", repr(e))
            pdf_bytes = None

        # Upload PDF if generated
        if pdf_bytes:
            class BytesUploadFile:
                def __init__(self, content: bytes):
                    self._content = content
                    self.file = io.BytesIO(content)
                    self.filename = f"trip_receipt_{uuid.uuid4().hex}.pdf"
                    self.content_type = "application/pdf"

                async def read(self):
                    return self._content

            pdf_file = BytesUploadFile(pdf_bytes)

            logger.info("[CONFIRM] Uploading PDF...")
            print("[CONFIRM] Uploading PDF...")
            
            confirmation = await handle_file_upload(
                app=confirmation,
                file=pdf_file,
                prefix=f"{org_id}/delivery/receipts",
                field_name="pdf_receipt",
                db=db,
                user_id=current_user.id if current_user else None,
                action="upload_pdf_receipt",
            )

            uploaded_s3_keys.append(getattr(confirmation, "pdf_receipt_path", None))

        logger.info("[CONFIRM] Committing DB...")
        print("[CONFIRM] Committing DB...")

        db.commit()
        db.refresh(confirmation)

        logger.info(f"[CONFIRM] DB commit OK | confirmation_id={confirmation.id}")
        print(f"[CONFIRM] DB commit OK | confirmation_id={confirmation.id}")

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"[CONFIRM] HARD FAIL 500: {e}")
        print("[CONFIRM] HARD FAIL 500:", repr(e))

        for key in uploaded_s3_keys:
            if not key:
                continue
            try:
                await delete_file_from_s3(key)
            except Exception as cleanup_err:
                logger.exception(f"[CONFIRM] Cleanup S3 failed: {cleanup_err}")
                print("[CONFIRM] Cleanup S3 failed:", repr(cleanup_err))

        raise HTTPException(status_code=500, detail=f"Delivery confirmation failed: {str(e)}")

    # --------------------------
    # Log activity (non-blocking)
    # --------------------------
    try:
        log_activity(
            db=db,
            user_id=current_user.id if current_user else None,
            action="delivery_confirmed",
            details=f"Trip {trip.id} confirmed | IP: {ip_address} | UA: {user_agent}",
        )
    except Exception as e:
        logger.exception(f"[CONFIRM] log_activity failed (ignored): {e}")
        print("[CONFIRM] log_activity failed (ignored):", repr(e))

    # --------------------------
    # Presigned URLs (non-blocking)
    # --------------------------
    presigned_urls = {}
    try:
        for field in [
            "pdf_receipt_path",
            "signature_image_path",
            "pickup_photo_path",
            "disposal_facility_signature_path",
            "dropoff_photo_path",
        ]:
            path = getattr(confirmation, field, None)
            if path:
                presigned_urls[field] = await generate_presigned_url_async(path)
    except Exception as e:
        logger.exception(f"[CONFIRM] presigned URL failed (ignored): {e}")
        print("[CONFIRM] presigned URL failed (ignored):", repr(e))

    # --------------------------
    # Email (non-blocking)
    # --------------------------
    try:
        # ✅ send to BOTH internal client + external client (avoid duplicates)
        attachments = []
        short_ref = str(trip.id)[:8]

        csv_buffer = io.StringIO()
        csv_writer = csv.writer(csv_buffer)

        csv_writer.writerow([
            "Trip ID",
            "Short Ref",
            "Client Name",
            "Client Email",
            "Driver Name",
            "WTN Code",
            "Pickup Timestamp",
            "Dropoff Timestamp",
            "Signature URL",
            "Pickup Photo URL",
            "Dropoff Photo URL",
            "Facility Name",
            "Facility Address",
            "Facility Signature URL",
            "Notes",
            "Latitude",
            "Longitude",
        ])

        csv_writer.writerow([
            str(trip.id),
            short_ref,
            confirmation.external_client_name,
            confirmation.external_client_email,
            getattr(trip, "driver_name", None),
            confirmation.wtn_code,
            confirmation.pickup_at,
            confirmation.dropoff_at,
            presigned_urls.get("signature_image_path"),
            presigned_urls.get("pickup_photo_path"),
            presigned_urls.get("dropoff_photo_path"),
            confirmation.disposal_facility_name,
            confirmation.disposal_facility_address,
            presigned_urls.get("disposal_facility_signature_path"),
            confirmation.extra_notes,
            confirmation.latitude,
            confirmation.longitude,
        ])

        csv_bytes = csv_buffer.getvalue().encode("utf-8")

        attachments.append({
            "ContentType": "text/csv",
            "Filename": f"trip_{short_ref}_confirmation.csv",
            "Base64Content": base64.b64encode(csv_bytes).decode("utf-8"),
        })

        if pdf_bytes:
            attachments.append({
                "ContentType": "application/pdf",
                "Filename": f"trip_{short_ref}_receipt.pdf",
                "Base64Content": base64.b64encode(pdf_bytes).decode("utf-8"),
            })

        # ✅ Collect recipients (external + internal), avoid duplicates
        recipients = set()

        if confirmation.external_client_email:
            recipients.add(confirmation.external_client_email.strip().lower())

        try:
            if getattr(trip, "client_id", None):
                client_user = db.query(User).filter(User.id == trip.client_id).first()
                if client_user and getattr(client_user, "email", None):
                    recipients.add(client_user.email.strip().lower())
        except Exception:
            pass

        # ✅ Send to everyone we found
        for email in recipients:
            logger.info(f"[CONFIRM] Sending email to {email}")
            print(f"[CONFIRM] Sending email to {email}")

            send_email(
                to_email=email,
                subject=f"Trip {short_ref} Delivered - Medilogic",
                body=(
                    f"Your trip ({short_ref}) has been successfully delivered.\n\n"
                    "Please find attached your delivery documents. "
                    "The CSV contains links to the signature and photos, plus facility details."
                ),
                attachments=attachments,
            )

        logger.info("[CONFIRM] Email sent OK")
        print("[CONFIRM] Email sent OK")

    except Exception as e:
        logger.exception(f"[CONFIRM] Email failed (ignored): {e}")
        print("[CONFIRM] Email failed (ignored):", repr(e))

    return {
        "message": "Delivery confirmed",
        "presigned_urls": presigned_urls,
    }