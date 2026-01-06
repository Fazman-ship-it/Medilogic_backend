# app/crud/delivery_confirmations.py

import uuid
from sqlalchemy.orm import Session
from app.models import DeliveryConfirmation, Trip
from datetime import datetime
from fastapi import HTTPException, status
from app.utilites.time_utilities import now_utc


def create_delivery_confirmation(
    db: Session,
    trip_id,  # accepts UUID or str
    organization_id,  # ✅ REQUIRED (multi-tenant)
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

    # --- Optional PIN check (ONLY if trip requires it) ---
    pin_required = getattr(trip, "requires_pin", False) or getattr(trip, "pin_required", False)
    if pin_required:
        if not pin_entered:
            raise HTTPException(status_code=400, detail="PIN is required")
        # Use your field name (you had trip.confirmation_pin)
        if getattr(trip, "confirmation_pin", None) and trip.confirmation_pin != pin_entered:
            raise HTTPException(status_code=401, detail="Invalid PIN")

    # --- Stop duplicates ---
    if getattr(trip, "is_delivered", False):
        raise HTTPException(status_code=400, detail="Trip already confirmed")

    confirmation = DeliveryConfirmation(
        trip_id=trip.id,
        organization_id=organization_id,  # ✅ store org_id
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
    )

    # Mark trip delivered (you already do this)
    trip.is_delivered = True
    trip.delivery_confirmed_at = confirmation.confirmed_at
    trip.delivery_ip = ip_address
    trip.wtn_serial = wtn_code

    db.add(confirmation)
    db.flush()          # ✅ don't commit here (endpoint commits)
    db.refresh(confirmation)
    return confirmation