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
from schemas import DeliveryConfirmationRequest, DeliveryConfirmationResponse
from app.utilites.helper import save_upload_file
from utilites.pdf_file_generator import generate_confirmation_pdf
from app.utilites.logging import log_activity

router = APIRouter(tags=["Delivery Confirmation"])
templates = Jinja2Templates(directory="templates")
SECRET_KEY = os.getenv("DELIVERY_CONFIRM_SECRET", "fallback_key")
ALGORITHM = "HS256"
UPLOAD_DIR = "app/static/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# === STEP 1: Redirect from QR Code Token ===
@router.get("/confirm", response_class=RedirectResponse)
def get_confirmation_form(token: str, db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        trip_id = payload.get("trip_id")
        org_id = payload.get("organization_id")

        if not trip_id or not org_id:
            raise HTTPException(status_code=400, detail="Invalid token payload")

        # Secure tenant-based query
        trip = db.query(Trip).filter(Trip.id == trip_id, Trip.organization_id == org_id).first()
        if not trip:
            raise HTTPException(status_code=404, detail="Trip not found or unauthorized")

        if trip.is_delivered:
            raise HTTPException(status_code=400, detail="Trip already confirmed")

        # Redirect to frontend confirmation form
        return RedirectResponse(
            url=f"{settings.FRONTEND_CONFIRM_SUCCESS_URL}?token={token}",
            status_code=302
        )

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

# === STEP 2: Show HTML Form (Optional if you use Frontend SPA) ===
from app.dependencies import get_current_user  # assuming you have this
from app.models import Trip, User

@router.get("/confirm-receipt/{trip_id}", response_class=HTMLResponse)
async def show_confirmation_form(
    request: Request,
    trip_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    trip = db.query(Trip).filter(
        Trip.id == trip_id,
        Trip.organization_id == current_user.organization_id  # restrict to same org
    ).first()

    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found or unauthorized")

    return templates.TemplateResponse("confirm_receipt.html", {
        "request": request,
        "trip_id": trip_id,
        "trip": trip
    })
# === STEP 3: Submit Delivery Confirmation ===
from app.dependencies import get_current_user  # Ensure this returns User with .organization_id
from app.models import Trip, User
from fastapi import status

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

    # 🔒 Enforce multi-tenancy
    trip = db.query(Trip).filter(
        Trip.id == trip_id,
        Trip.organization_id == current_user.organization_id  # ✅ Enforce tenant restriction
    ).first()

    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found or unauthorized"
        )

    # Save uploaded files
    signature_path = save_upload_file(signature_image, subfolder="static/signatures") if signature_image else None
    photo_path = save_upload_file(photo, subfolder="static/photos") if photo else None

    # Create delivery confirmation record
    confirmation = create_delivery_confirmation(
        db=db,
        trip_id=str(trip_id),
        pin=pin,
        signature_path=signature_path,
        photo_path=photo_path,
        wtn_code=wtn_code,
        ip_address=ip_address,
        user_agent=user_agent,
        latitude=latitude,
        longitude=longitude
    )

    # Generate PDF receipt
    pdf_path = generate_confirmation_pdf(confirmation)

    # Log action
    log_activity(
        db=db,
        user_id=current_user.id,
        action="delivery_confirmed",
        details=f"Trip {trip_id} confirmed | IP: {ip_address} | UA: {user_agent}"
    )

    return {
        "message": "Delivery confirmed",
        "pdf_receipt": pdf_path.replace("static/", "/static/")
    }