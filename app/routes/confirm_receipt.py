# app/routes/confirm_receipt.py
from fastapi import APIRouter, Request, Depends, HTTPException, status, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from uuid import UUID
from datetime import datetime
import os, uuid, jwt
from app.database import get_db
from app.models import Trip
from app.config import settings
from app.crudy.delivery_confirmation import create_delivery_confirmation
from  app.schemas import DeliveryConfirmationRequest, DeliveryConfirmationResponse
from app.utilites.helper import save_upload_file
from app.utilites.pdf_file_generator import generate_confirmation_pdf
from app.utilites.logging import log_activity

import uuid
from fastapi import APIRouter, Form, File, UploadFile, Request, Depends, HTTPException, status
from fastapi.responses import RedirectResponse, HTMLResponse
from app.dependencies import get_current_user
from app.models import Trip, User
from sqlalchemy.orm import Session
from app.database import get_db
from app.utilites.storage_utilites import upload_file_to_s3, generate_presigned_url  # your S3 helpers
from app.crudy import create_delivery_confirmation
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
        trip_id = payload.get("trip_id")
        org_id = payload.get("organization_id")

        if not trip_id or not org_id:
            raise HTTPException(status_code=400, detail="Invalid token payload")

        trip = db.query(Trip).filter(Trip.id == trip_id, Trip.organization_id == org_id).first()
        if not trip:
            raise HTTPException(status_code=404, detail="Trip not found or unauthorized")

        if trip.is_delivered:
            raise HTTPException(status_code=400, detail="Trip already confirmed")

        return RedirectResponse(
            url=f"{settings.FRONTEND_CONFIRM_SUCCESS_URL}?token={token}",
            status_code=302
        )

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

# === STEP 2: Show HTML Form (Optional if using SPA) ===
@router.get("/confirm-receipt/{trip_id}", response_class=HTMLResponse)
async def show_confirmation_form(
    request: Request,
    trip_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    trip = db.query(Trip).filter(
        Trip.id == trip_id,
        Trip.organization_id == current_user.organization_id
    ).first()

    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found or unauthorized")

    return templates.TemplateResponse("confirm_receipt.html", {
        "request": request,
        "trip_id": trip_id,
        "trip": trip
    })

# === STEP 3: Submit Delivery Confirmation ===
@router.post("/confirm", tags=["Delivery Confirmation"])
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

    trip = db.query(Trip).filter(
        Trip.id == trip_id,
        Trip.organization_id == current_user.organization_id
    ).first()

    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found or unauthorized"
        )

    # -------------------------
    # Upload files to S3
    # -------------------------
    signature_s3_key = None
    photo_s3_key = None

    if signature_image:
        signature_bytes = await signature_image.read()
        signature_s3_key = f"delivery/signatures/{uuid.uuid4()}_{signature_image.filename}"
        upload_file_to_s3(signature_bytes, signature_s3_key, signature_image.content_type)

    if photo:
        photo_bytes = await photo.read()
        photo_s3_key = f"delivery/photos/{uuid.uuid4()}_{photo.filename}"
        upload_file_to_s3(photo_bytes, photo_s3_key, photo.content_type)

    # -------------------------
    # Create delivery confirmation record
    # -------------------------
    confirmation = create_delivery_confirmation(
        db=db,
        trip_id=str(trip_id),
        pin=pin,
        signature_path=signature_s3_key,
        photo_path=photo_s3_key,
        wtn_code=wtn_code,
        ip_address=ip_address,
        user_agent=user_agent,
        latitude=latitude,
        longitude=longitude
    )

    # -------------------------
    # Generate PDF receipt and upload to S3
    # -------------------------
    pdf_bytes = generate_confirmation_pdf(confirmation)  # must return bytes
    pdf_s3_key = f"delivery/receipts/{uuid.uuid4()}_receipt.pdf"
    upload_file_to_s3(pdf_bytes, pdf_s3_key, "application/pdf")
    pdf_url = generate_presigned_url(pdf_s3_key)

    # -------------------------
    # Log action
    # -------------------------
    log_activity(
        db=db,
        user_id=current_user.id,
        action="delivery_confirmed",
        details=f"Trip {trip_id} confirmed | IP: {ip_address} | UA: {user_agent}"
    )

    return {
        "message": "Delivery confirmed",
        "pdf_receipt": pdf_url,
        "signature_url": generate_presigned_url(signature_s3_key) if signature_s3_key else None,
        "photo_url": generate_presigned_url(photo_s3_key) if photo_s3_key else None
    }