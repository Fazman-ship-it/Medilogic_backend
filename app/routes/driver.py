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
from app.utilites.time_utilities import now_utc
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