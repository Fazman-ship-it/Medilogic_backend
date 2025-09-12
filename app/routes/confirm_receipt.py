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

# === STEP 1: Redirect from QR Code Token ===
@router.get("/confirm", response_class=RedirectResponse)
def get_confirmation_form(token: str, db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        trip_id_str = payload.get("trip_id")
        org_id_str = payload.get("organization_id")

        if not trip_id_str or not org_id_str:
            raise HTTPException(status_code=400, detail="Invalid token payload")

        # ✅ Convert to UUID for safety
        try:
            trip_id = UUID(trip_id_str)
            org_id = UUID(org_id_str)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid UUID in token")

        trip = db.query(Trip).filter(
            Trip.id == trip_id,
            Trip.organization_id == org_id
        ).first()

        if not trip:
            raise HTTPException(status_code=404, detail="Trip not found or unauthorized")

        if trip.is_delivered:
            raise HTTPException(status_code=400, detail="Trip already confirmed")

        # ✅ Redirect to frontend confirmation page
        return RedirectResponse(
            url=f"{settings.FRONTEND_CONFIRM_SUCCESS_URL}?token={token}",
            status_code=302
        )

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
from app.crud import create_delivery_confirmation
import uuid
import io

@router.post("/confirm", tags=["Delivery Confirmation"], response_model=DeliveryConfirmationResponse)
async def submit_delivery_confirmation(
    trip_id: UUID = Form(...),
    pin: str = Form(...),
    wtn_code: str = Form(None),
    latitude: float = Form(None),
    longitude: float = Form(None),
    signature_image: UploadFile = File(None),
    photo: UploadFile = File(None),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    ip_address = request.client.host
    user_agent = request.headers.get("user-agent")

    # -------------------------
    # Validate trip
    # -------------------------
    trip = db.query(Trip).filter(
        Trip.id == trip_id,
        Trip.organization_id == current_user.organization_id
    ).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found or unauthorized")
    if trip.is_delivered:
        raise HTTPException(status_code=400, detail="Trip already confirmed")

    # -------------------------
    # Validate inputs
    # -------------------------
    if len(pin.strip()) < 4:
        raise HTTPException(status_code=400, detail="PIN too short")
    if latitude and not (-90 <= latitude <= 90):
        raise HTTPException(status_code=400, detail="Invalid latitude")
    if longitude and not (-180 <= longitude <= 180):
        raise HTTPException(status_code=400, detail="Invalid longitude")

    uploaded_s3_keys = []
    confirmation = None

    try:
        # -------------------------
        # DB transaction: create confirmation record first
        # -------------------------
        confirmation = create_delivery_confirmation(
            db=db,
            trip_id=trip_id,
            pin=pin,
            wtn_code=wtn_code,
            ip_address=ip_address,
            user_agent=user_agent,
            latitude=latitude,
            longitude=longitude
        )

        # -------------------------
        # Upload signature and photo using helper
        # -------------------------
        if signature_image:
            confirmation = await handle_file_upload(
                app=confirmation,
                file=signature_image,
                prefix="delivery/signatures",
                field_name="signature",
                db=db,
                user_id=current_user.id,
                action="upload_signature"
            )
            uploaded_s3_keys.append(getattr(confirmation, "signature_path"))

        if photo:
            confirmation = await handle_file_upload(
                app=confirmation,
                file=photo,
                prefix="delivery/photos",
                field_name="photo",
                db=db,
                user_id=current_user.id,
                action="upload_photo"
            )
            uploaded_s3_keys.append(getattr(confirmation, "photo_path"))

        # -------------------------
        # Generate PDF receipt and upload using helper
        # -------------------------
        pdf_bytes = generate_confirmation_pdf(confirmation)
        class BytesUploadFile:
            """Wrap raw bytes into a file-like object compatible with handle_file_upload"""
            def __init__(self, content: bytes):
                self.file = io.BytesIO(content)
                self.filename = f"receipt_{uuid.uuid4().hex}.pdf"
                self.content_type = "application/pdf"
                
        pdf_file = BytesUploadFile(pdf_bytes)

        confirmation = await handle_file_upload(
            app=confirmation,
            file=pdf_file,
            prefix="delivery/receipts",
            field_name="pdf_receipt",
            db=db,
            user_id=current_user.id,
            action="generate_pdf_receipt"
        )
        uploaded_s3_keys.append(getattr(confirmation, "pdf_receipt_path"))

    except Exception as e:
        db.rollback()
        # Cleanup uploaded files if anything fails
        from app.utilites.storage_utilites import delete_file_from_s3
        for key in uploaded_s3_keys:
            try:
                await delete_file_from_s3(key)
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=f"Delivery confirmation failed: {str(e)}")

    # -------------------------
    # Log action
    # -------------------------
    log_activity(
        db=db,
        user_id=current_user.id,
        action="delivery_confirmed",
        details=f"Trip {trip_id} confirmed | IP: {ip_address} | UA: {user_agent} | "
                f"Files: {getattr(confirmation,'signature_path')}, {getattr(confirmation,'photo_path')}, {getattr(confirmation,'pdf_receipt_path')}"
    )

    # -------------------------
    # Return presigned URLs
    # -------------------------
    pdf_url = await generate_presigned_url_async(getattr(confirmation, "pdf_receipt_path")) if getattr(confirmation, "pdf_receipt_path") else None
    signature_url = await generate_presigned_url_async(getattr(confirmation, "signature_path")) if getattr(confirmation, "signature_path") else None
    photo_url = await generate_presigned_url_async(getattr(confirmation, "photo_path")) if getattr(confirmation, "photo_path") else None

    return {
        "message": "Delivery confirmed",
        "pdf_receipt": pdf_url,
        "signature_url": signature_url,
        "photo_url": photo_url
    }
