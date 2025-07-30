# app/crud/delivery_confirmations.py

import uuid
from sqlalchemy.orm import Session
from app.models import DeliveryConfirmation, Trip
from datetime import datetime
from fastapi import HTTPException, status

def create_delivery_confirmation(
    db: Session,
    trip_id: str,
    pin: str,
    signature_path: str = None,
    photo_path: str = None,
    wtn_code: str = None,
    ip_address: str = None,
    user_agent: str = None,
    latitude: float = None,
    longitude: float = None

):
    trip = db.query(Trip).filter(Trip.id == uuid.UUID(trip_id)).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    if trip.confirmation_pin != pin:
        raise HTTPException(status_code=401, detail="Invalid PIN")

    if trip.is_delivered:
        raise HTTPException(status_code=400, detail="Trip already confirmed")

    confirmation = DeliveryConfirmation(
        trip_id=trip.id,
        pin_entered=pin,
        signature_image_path=signature_path,
        photo_path=photo_path,
        wtn_code=wtn_code,
        confirmed_at=datetime.utcnow(),
        ip_address=ip_address,
        user_agent=user_agent,
        organization_id=trip.organization_id,
        latitude=latitude,
        longitude=longitude
    )

    # Update Trip delivery info
    trip.is_delivered = True
    trip.delivery_confirmed_at = confirmation.confirmed_at
    trip.confirmation_photo_path = photo_path# we store paths in DeliveryConfirmation only
    trip.delivery_signature_path = signature_path
    trip.delivery_ip = ip_address
    trip.wtn_serial = wtn_code

    db.add(confirmation)
    db.commit()
    db.refresh(confirmation)
    return confirmation