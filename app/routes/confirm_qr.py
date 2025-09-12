# app/routes/confirm_qr.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Trip
from app. utilites.token import generate_delivery_token
from app.config import settings
import uuid
from app.utilites.qr import generate_qr_code_base64
from uuid import UUID
router = APIRouter(prefix="/confirm", tags=["Delivery Confirmation"])

@router.post("/generate-confirmation-link")
def generate_confirmation_link(
    trip_id: UUID,  # ✅ FastAPI automatically validates UUID
    db: Session = Depends(get_db)
):
    # Fetch trip by UUID
    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    # Ensure multi-tenant / org context exists
    if not trip.organization_id:
        raise HTTPException(status_code=400, detail="Trip is missing organization context")

    # Generate delivery token
    token = generate_delivery_token(str(trip.id), str(trip.organization_id))
    confirmation_url = f"{settings.DELIVERY_CONFIRMATION_URL}{token}"

    return {
        "trip_id": str(trip.id),
        "organization_id": str(trip.organization_id),
        "confirmation_url": confirmation_url,
        "expires_in_minutes": settings.DELIVERY_CONFIRM_EXPIRY_MINUTES
    }
    


@router.post("/generate-qr-code")
def generate_qr_code_endpoint(
    trip_id: UUID,  # ✅ FastAPI automatically validates UUID
    db: Session = Depends(get_db)
):
    # Fetch trip
    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    if not trip.organization_id:
        raise HTTPException(status_code=400, detail="Trip is missing organization context")

    # Generate token and confirmation URL
    token = generate_delivery_token(str(trip.id), str(trip.organization_id))
    confirmation_url = f"{settings.DELIVERY_CONFIRMATION_URL}{token}"

    # Generate QR code as base64
    qr_base64 = generate_qr_code_base64(confirmation_url)

    return {
        "trip_id": str(trip.id),
        "organization_id": str(trip.organization_id),
        "confirmation_url": confirmation_url,
        "qr_code_base64": qr_base64
    }