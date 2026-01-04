from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app import models 
from app.database import get_db
from app.dependencies import get_current_user
from pydantic import BaseModel
from app.utilites.logging import log_activity
from app.schemas import LocationUpdate
from datetime import datetime
from typing import List
from app.models import User
from app.schemas import DriverLocationHistoryOut
from uuid import UUID
router = APIRouter(
    prefix="/drivers",
    tags=["Drivers"]
)

from app.models import DriverLocationHistory
from app.utilites.time_utilities import now_utc, to_local, to_utc
@router.patch("/location")
def update_driver_location(
    location: LocationUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role != "driver":
        raise HTTPException(status_code=403, detail="Only drivers can update location.")

    # Update current location
    current_user.latitude = location.latitude
    current_user.longitude = location.longitude
    current_user.last_location_update = now_utc()

    # ✅ Save to location history
    location_entry = DriverLocationHistory(
        driver_id=current_user.id,
        latitude=location.latitude,
        longitude=location.longitude
    )
    db.add(location_entry)

    db.commit()

    log_activity(
        db=db,
        user_id=current_user.id,
        action="driver_location_updated",
        details=f"Driver {current_user.name} updated location to ({location.latitude}, {location.longitude})"
    )

    return {"message": "Driver location updated successfully."}


# ✅ GET current driver's location
@router.get("/location")
def get_driver_location(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role != "driver":
        raise HTTPException(status_code=403, detail="Only drivers can access this endpoint.")

    return {
        "latitude": current_user.latitude,
        "longitude": current_user.longitude,
        "last_updated": current_user.last_location_update
    }

@router.get("/{driver_id}/location")
def get_driver_location_by_id(
    driver_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Only admins or super admins can access this.")

    # 👇 Super Admin: unrestricted access
    if current_user.role == "super_admin":
        driver = db.query(models.User).filter_by(id=driver_id, role="driver").first()
    else:
        # 👇 Admin: restricted to their own organization only
        driver = db.query(models.User).filter_by(
            id=driver_id,
            role="driver",
            organization_id=current_user.organization_id
        ).first()

    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found or access denied.")

    return {
        "driver_id": driver.id,
        "latitude": driver.latitude,
        "longitude": driver.longitude,
        "last_updated": driver.last_location_update
    }
    
@router.get("/location/history", response_model=List[DriverLocationHistoryOut])
def get_driver_location_history(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role != "driver":
        raise HTTPException(status_code=403, detail="Only drivers can access this endpoint.")

    history = db.query(DriverLocationHistory)\
        .filter(DriverLocationHistory.driver_id == current_user.id)\
        .order_by(DriverLocationHistory.timestamp.desc())\
        .all()

    return history

@router.get("/drivers/{driver_id}/location/history", response_model=List[DriverLocationHistoryOut])
def get_driver_location_history_by_id(
    driver_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Not authorized.")

    driver = db.query(User).filter(User.id == driver_id).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found.")

    if current_user.role == "admin" and current_user.organization_id != driver.organization_id:
        raise HTTPException(status_code=403, detail="Cannot access drivers from other organizations.")

    history = db.query(DriverLocationHistory)\
        .filter(DriverLocationHistory.driver_id == driver_id)\
        .order_by(DriverLocationHistory.timestamp.desc())\
        .all()

    return history
    
    
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, case
from typing import Optional
from uuid import UUID
from datetime import datetime
from app import models
from app.database import get_db
from app.dependencies import get_current_user
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from uuid import UUID
from app.schemas import DriverTrip, DriverDashboardResponse
from datetime import datetime
from app import models
from app.database import get_db
from app.dependencies import get_current_user
from app.utilites.time_utilities import to_utc, to_local, now_utc, now_local  # ✅ Same helper used in admin trips



@router.get("/driver/{driver_id}/trips", summary="Get all trips assigned to a driver")
def get_driver_trips(
    driver_id: UUID,
    status: Optional[str] = Query(None, description="Filter by trip status"),
    delivery_type: Optional[str] = Query(None, description="Filter by delivery type"),
    start_date: Optional[datetime] = Query(None, description="Start of date range"),
    end_date: Optional[datetime] = Query(None, description="End of date range"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Retrieve all trips assigned to a specific driver.
    - Drivers can view only their own trips.
    - Admins and managers can view any driver’s trips.
    - Sorted so most recent trips appear first for better UX.
    """

    # ✅ Access Control
    if current_user.role == "client":
        raise HTTPException(status_code=403, detail="Clients cannot view driver trips.")

    if current_user.role == "driver" and current_user.id != driver_id:
        raise HTTPException(status_code=403, detail="You can only view your own assigned trips.")

    # ✅ Base Query
    query = db.query(models.Trip).filter(
        models.Trip.driver_id == driver_id,
        models.Trip.organization_id == current_user.organization_id
    )

    # ✅ Apply filters
    if status:
        query = query.filter(models.Trip.status.ilike(f"%{status}%"))
    if delivery_type:
        query = query.filter(models.Trip.delivery_type.ilike(f"%{delivery_type}%"))
    if start_date and end_date:
        query = query.filter(models.Trip.scheduled_time.between(start_date, end_date))

    # ✅ UX Enhancement: Show most recent trips first
    # Sort by scheduled_time DESC, fallback to created_at if scheduled_time is NULL
    trips = query.order_by(
        desc(
            case(
                (models.Trip.scheduled_time != None, models.Trip.scheduled_time),
                else_=models.Trip.created_at
            )
        )
    ).all()

    # ✅ Convert timestamps to local time
    for t in trips:
        if t.scheduled_time:
            t.scheduled_time = to_local(t.scheduled_time)
        if t.created_at:
            t.created_at = to_local(t.created_at)

    # ✅ Return structured trip info
    return {
    "driver_id": driver_id,
    "total_trips": len(trips),
    "assigned_trips": [
        {
            "trip_id": t.id,
            # 👇 Trip label now shows the custom description when delivery_type == 'others'
            "trip_label": f"{t.client_name} — {(
                t.custom_delivery_description
                if t.delivery_type and str(t.delivery_type).lower() == 'others'
                else (t.delivery_type or 'Unspecified')
            )}",
            # 👇 delivery_type field also matches custom text for 'others'
            "delivery_type": (
                t.custom_delivery_description
                if t.delivery_type and str(t.delivery_type).lower() == "others"
                else (t.delivery_type if t.delivery_type else None)
            ),
            "client_name": t.client_name,
            "pickup_location": t.pickup_location,
            "dropoff_location": t.dropoff_location,
            "scheduled_time": t.scheduled_time,
            "created_at": t.created_at,
            "status": t.status,
            "priority": t.priority,
            "vehicle_type": t.vehicle_type,
            "distance_km": t.distance_km,
            "cost": t.cost,
            "compliance_flag": t.compliance_flag,
            "shift_window": t.shift_window,
            "recurrence_rule": t.recurrence_rule,
            "notes": t.notes,
            "custom_delivery_description": t.custom_delivery_description,
        }
        for t in trips
    ]
}


# ✅ Optional: Auto-detect driver from JWT (for mobile apps)
# @router.get("/driver/trips", summary="Get all trips for the logged-in driver")
# def get_my_trips(
#     db: Session = Depends(get_db),
#     current_user: models.User = Depends(require_role("driver"))
# ):
#     return get_driver_trips(
#         driver_id=current_user.id,
#         db=db,
#         current_user=current_user
#     )

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from uuid import UUID
from datetime import timedelta
import qrcode
import base64
from io import BytesIO
from app.dependencies import get_db, get_current_user
from app.models import Trip, DeliveryConfirmation, User
from app.config import settings
from app.auth import create_access_token
from app. utilites.qr import generate_qr_code_base64
from app.utilites.time_utilities import now_utc

@router.get("/trips/{trip_id}/confirmation", response_model=dict)
async def get_driver_trip_confirmation(
    trip_id: UUID,
    include_qr: bool = Query(True, description="Set false to skip QR generation"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Only drivers
    if current_user.role != "driver":
        raise HTTPException(status_code=403, detail="Only drivers can access this endpoint")

    # Fetch trip (multi-tenant + driver check)
    trip = db.query(Trip).filter(
        Trip.id == trip_id,
        Trip.driver_id == current_user.id,
        Trip.organization_id == current_user.organization_id
    ).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found or not assigned to you")

    # Fetch or create delivery confirmation
    confirmation = db.query(DeliveryConfirmation).filter(
        DeliveryConfirmation.trip_id == trip.id,
        DeliveryConfirmation.organization_id == current_user.organization_id
    ).first()

    if not confirmation:
        # Create new confirmation with token
        from uuid import uuid4
        confirmation = DeliveryConfirmation(
            trip_id=trip.id,
            organization_id=trip.organization_id,
            pin_entered="N/A",
            access_token=uuid4().hex,
            token_expires_at=now_utc() + timedelta(minutes=settings.DELIVERY_CONFIRM_EXPIRY_MINUTES)
        )
        db.add(confirmation)
        db.commit()
        db.refresh(confirmation)
    else:
        # Re-issue token if expired
        if not confirmation.access_token or confirmation.token_expires_at < now_utc():
            from uuid import uuid4
            confirmation.access_token = uuid4().hex
            confirmation.token_expires_at = now_utc() + timedelta(minutes=settings.DELIVERY_CONFIRM_EXPIRY_MINUTES)
            db.add(confirmation)
            db.commit()
            db.refresh(confirmation)

    # Generate short-lived JWT for QR
    jwt_token = create_access_token(
        data={"trip_id": str(trip.id), "organization_id": str(trip.organization_id)},
        expires_delta=timedelta(minutes=settings.DELIVERY_CONFIRM_EXPIRY_MINUTES)
    )
    confirmation_url = f"{settings.DELIVERY_CONFIRMATION_URL}{jwt_token}"

    # Optional QR generation
    qr_base64 = None
    if include_qr:
        qr_base64 = generate_qr_code_base64(confirmation_url)

    return {
        "trip_id": str(trip.id),
        "driver_name": trip.driver_name,
        "client_name": getattr(trip, "client_name", None),
        "delivery_type": trip.delivery_type,
        "pickup_location": trip.pickup_location,
        "dropoff_location": trip.dropoff_location,
        "scheduled_time": trip.scheduled_time,
        "confirmation_url": confirmation_url,
        "qr_code_base64": qr_base64,
        "token_expires_at": confirmation.token_expires_at,
        "status": "pending" if confirmation.signature_image_path is None else "completed"
    }
    
@router.get(
    "/driver/{driver_id}/trips/{trip_id}",
    summary="Get a single trip assigned to a driver"
)
def get_driver_single_trip(
    driver_id: UUID,
    trip_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Retrieve a single trip assigned to a specific driver.
    - Drivers can view only their own trips
    - Admins/managers can view any driver trip in their organisation
    """

    # 🚫 Clients cannot access driver trips
    if current_user.role == "client":
        raise HTTPException(status_code=403, detail="Clients cannot view driver trips.")

    # 🚫 Drivers can only view their own trips
    if current_user.role == "driver" and current_user.id != driver_id:
        raise HTTPException(
            status_code=403,
            detail="You can only view your own assigned trips."
        )

    # ✅ Fetch trip (multi-tenant + driver check)
    trip = db.query(models.Trip).filter(
        models.Trip.id == trip_id,
        models.Trip.driver_id == driver_id,
        models.Trip.organization_id == current_user.organization_id
    ).first()

    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    # 🕒 Convert timestamps to local time
    if trip.scheduled_time:
        trip.scheduled_time = to_local(trip.scheduled_time)
    if trip.created_at:
        trip.created_at = to_local(trip.created_at)

    # ✅ Build response (same shape as list item)
    return {
        "trip_id": trip.id,

        "trip_label": f"{trip.client_name} — {(
            trip.custom_delivery_description
            if trip.delivery_type and str(trip.delivery_type).lower() == 'others'
            else (trip.delivery_type or 'Unspecified')
        )}",

        "delivery_type": (
            trip.custom_delivery_description
            if trip.delivery_type and str(trip.delivery_type).lower() == "others"
            else (trip.delivery_type if trip.delivery_type else None)
        ),

        "client_name": trip.client_name,
        "pickup_location": trip.pickup_location,
        "dropoff_location": trip.dropoff_location,
        "scheduled_time": trip.scheduled_time,
        "created_at": trip.created_at,
        "status": trip.status,
        "priority": trip.priority,
        "vehicle_type": trip.vehicle_type,
        "distance_km": trip.distance_km,
        "cost": trip.cost,
        "compliance_flag": trip.compliance_flag,
        "shift_window": trip.shift_window,
        "recurrence_rule": trip.recurrence_rule,
        "notes": trip.notes,
        "custom_delivery_description": trip.custom_delivery_description,
    }