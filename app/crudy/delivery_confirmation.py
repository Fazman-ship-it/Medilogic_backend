# app/crud/delivery_confirmations.py

import uuid
from sqlalchemy.orm import Session
from app.models import DeliveryConfirmation, Trip
from datetime import datetime
from fastapi import HTTPException, status
from app.utilites.time_utilities import now_utc
from typing import Optional

def create_delivery_confirmation(
    db: Session,
    trip_id,
    organization_id,
    pin_entered: Optional[str] = None,
    external_client_name: Optional[str] = None,
    external_client_email: Optional[str] = None,
    wtn_code: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    extra_notes: Optional[str] = None,
    pickup_at: Optional[datetime] = None,
    dropoff_at: Optional[datetime] = None,
    disposal_facility_name: Optional[str] = None,
    disposal_facility_address: Optional[str] = None,
):
    # --- Normalize trip_id to UUID ---
    try:
        trip_uuid = trip_id if isinstance(trip_id, uuid.UUID) else uuid.UUID(str(trip_id))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid trip_id")

    # --- Fetch trip (org-safe) ---
    trip = db.query(Trip).filter(
        Trip.id == trip_uuid,
        Trip.organization_id == organization_id
    ).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found or unauthorized")

    # --- Optional PIN check (STRICT) ---
    pin_required = bool(getattr(trip, "requires_pin", False) or getattr(trip, "pin_required", False))
    if pin_required:
        if not pin_entered:
            raise HTTPException(status_code=400, detail="PIN is required")

        # ✅ if requires_pin is enabled, the trip MUST have a confirmation_pin
        if not getattr(trip, "confirmation_pin", None):
            raise HTTPException(status_code=400, detail="This trip requires a PIN but no PIN is set. Contact admin.")

        if trip.confirmation_pin != pin_entered:
            raise HTTPException(status_code=401, detail="Invalid PIN")

    # ✅ IMPORTANT CHANGE:
    # Do NOT block on trip.is_delivered here, because pickup can be saved first,
    # and delivery is finalised later when dropoff_photo is uploaded.
    # Duplicate/finalisation control belongs in the endpoint.

    confirmation = DeliveryConfirmation(
        trip_id=trip.id,
        organization_id=organization_id,
        pin_entered=pin_entered,

        wtn_code=wtn_code,

        confirmed_at=now_utc(),
        ip_address=ip_address,
        user_agent=user_agent,
        latitude=latitude,
        longitude=longitude,

        pickup_at=pickup_at,
        dropoff_at=dropoff_at,

        external_client_name=external_client_name,
        external_client_email=external_client_email,
        extra_notes=extra_notes,
        disposal_facility_name=disposal_facility_name,
        disposal_facility_address=disposal_facility_address,
    )

    # ✅ IMPORTANT CHANGE:
    # Do NOT mark trip delivered here.
    # Trip should only be set delivered in the endpoint when dropoff_photo is provided.

    # ✅ Still safe to set wtn_serial if provided (optional)
    if wtn_code:
        trip.wtn_serial = wtn_code

    db.add(confirmation)
    db.flush()
    return confirmation