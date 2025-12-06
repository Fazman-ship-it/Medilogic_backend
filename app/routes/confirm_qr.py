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
from app.dependencies import get_current_user
router = APIRouter(prefix="/confirm", tags=["Delivery Confirmation"])

# -----------------------------
# Helpers
# -----------------------------
def generate_access_token() -> str:
    return uuid.uuid4().hex


@router.post("/generate-confirmation-link")
def generate_confirmation_link(
    trip_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # ✅ Multi-tenant trip fetch
    trip = db.query(Trip).filter(
        Trip.id == trip_id,
        Trip.organization_id == current_user.organization_id
    ).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found or unauthorized")

    # Fetch or create delivery confirmation
    confirmation = db.query(DeliveryConfirmation).filter(
        DeliveryConfirmation.trip_id == trip.id
    ).first()
    
    if not confirmation:
        confirmation = DeliveryConfirmation(
            trip_id=trip.id,
            organization_id=trip.organization_id,
            pin_entered="N/A",
            access_token=generate_access_token(),
            token_expires_at=datetime.utcnow() + timedelta(
                minutes=settings.DELIVERY_CONFIRM_EXPIRY_MINUTES
            )
        )
        db.add(confirmation)
        db.commit()
        db.refresh(confirmation)
    else:
        # Re-issue token if expired
        if not confirmation.access_token or confirmation.token_expires_at < datetime.utcnow():
            confirmation.access_token = generate_access_token()
            confirmation.token_expires_at = datetime.utcnow() + timedelta(
                minutes=settings.DELIVERY_CONFIRM_EXPIRY_MINUTES
            )
            db.add(confirmation)
            db.commit()
            db.refresh(confirmation)

    confirmation_url = f"{settings.DELIVERY_CONFIRMATION_URL}{confirmation.access_token}"
    return {
        "trip_id": str(trip.id),
        "organization_id": str(trip.organization_id),
        "confirmation_url": confirmation_url,
        "expires_in_minutes": settings.DELIVERY_CONFIRM_EXPIRY_MINUTES
    }


@router.post("/generate-qr-code")
def generate_qr_code_endpoint(
    trip_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # ✅ Multi-tenant trip fetch
    trip = db.query(Trip).filter(
        Trip.id == trip_id,
        Trip.organization_id == current_user.organization_id
    ).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found or unauthorized")

    # Fetch or create delivery confirmation
    confirmation = db.query(DeliveryConfirmation).filter(
        DeliveryConfirmation.trip_id == trip.id
    ).first()

    if not confirmation:
        confirmation = DeliveryConfirmation(
            trip_id=trip.id,
            organization_id=trip.organization_id,
            pin_entered="N/A",
            access_token=generate_access_token(),
            token_expires_at=datetime.utcnow() + timedelta(
                minutes=settings.DELIVERY_CONFIRM_EXPIRY_MINUTES
            )
        )
        db.add(confirmation)
        db.commit()
        db.refresh(confirmation)
    else:
        # Re-issue token if expired
        if not confirmation.access_token or confirmation.token_expires_at < datetime.utcnow():
            confirmation.access_token = generate_access_token()
            confirmation.token_expires_at = datetime.utcnow() + timedelta(
                minutes=settings.DELIVERY_CONFIRM_EXPIRY_MINUTES
            )
            db.add(confirmation)
            db.commit()
            db.refresh(confirmation)

    confirmation_url = f"{settings.DELIVERY_CONFIRMATION_URL}{confirmation.access_token}"
    qr_base64 = generate_qr_code_base64(confirmation_url)

    return {
        "trip_id": str(trip.id),
        "organization_id": str(trip.organization_id),
        "confirmation_url": confirmation_url,
        "qr_code_base64": qr_base64
    }