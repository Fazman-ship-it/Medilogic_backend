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


@router.post("/confirm", response_model=dict)
async def submit_delivery_confirmation(
    trip_id: UUID = Form(...),
    pin: str = Form(...),
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
    ip_address = request.client.host
    user_agent = request.headers.get("user-agent")

    # Validate email
    external_client_email = validate_email(external_client_email)

    # Fetch trip
    trip = db.query(Trip).filter(
        Trip.id == trip_id,
        Trip.organization_id == current_user.organization_id
    ).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found or unauthorized")
    if trip.is_delivered:
        raise HTTPException(status_code=400, detail="Trip already delivered")

    # Validate inputs
    if len(pin.strip()) < 4:
        raise HTTPException(status_code=400, detail="PIN too short")
    if latitude and not (-90 <= latitude <= 90):
        raise HTTPException(status_code=400, detail="Invalid latitude")
    if longitude and not (-180 <= longitude <= 180):
        raise HTTPException(status_code=400, detail="Invalid longitude")

    uploaded_s3_keys = []
    confirmation = None

    try:
        # --- Create or fetch delivery confirmation ---
        confirmation = create_delivery_confirmation(
            db=db,
            trip_id=trip_id,
            pin_entered=pin,
            external_client_name=external_client_name,
            external_client_email=external_client_email,
            wtn_code=wtn_code,
            ip_address=ip_address,
            user_agent=user_agent,
            latitude=latitude,
            longitude=longitude,
            extra_notes=extra_notes,
            pickup_at=now_utc,   # pickup timestamp
            dropoff_at=now_utc   # dropoff timestamp
        )

        # --- Upload files ---
        file_mapping = {
            "signature_image_path": signature_image,
            "pickup_photo_path": pickup_photo,
            "disposal_facility_signature_path": facility_signature,
            "dropoff_photo_path": dropoff_photo
        }

        for field_name, upload_file in file_mapping.items():
            if upload_file:
                confirmation = await handle_file_upload(
                    app=confirmation,
                    file=upload_file,
                    prefix=f"delivery/{field_name}",
                    field_name=field_name,
                    db=db,
                    user_id=current_user.id,
                    action=f"upload_{field_name}"
                )
                uploaded_s3_keys.append(getattr(confirmation, field_name))
                # --- Generate PDF receipt ---
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
            prefix="delivery/receipts",
            field_name="pdf_receipt_path",
            db=db,
            user_id=current_user.id,
            action="upload_pdf_receipt"
        )
        uploaded_s3_keys.append(getattr(confirmation, "pdf_receipt_path"))

        db.commit()

    except Exception as e:
        db.rollback()
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

    # --- Prepare CSV & PDF for email ---
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
    csv_bytes = csv_buffer.getvalue().encode()

    attachments = [
        {"ContentType": "text/csv",
         "Filename": f"trip_{trip.id}_confirmation.csv",
         "Base64Content": csv_bytes.decode('utf-8')},
        {"ContentType": "application/pdf",
         "Filename": f"trip_{trip.id}_receipt.pdf",
         "Base64Content": pdf_bytes.decode('latin1')}
    ]

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