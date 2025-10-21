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
from typing import Optional
from uuid import UUID
from datetime import datetime
from app import models
from app.database import get_db
from app.dependencies import get_current_user

router = APIRouter(prefix="/dashboard", tags=["Driver Dashboard"])

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
    Drivers can view only their own trips.
    Admins and managers can view any driver’s trips.
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
        query = query.filter(models.Trip.status == status)
    if delivery_type:
        query = query.filter(models.Trip.delivery_type == delivery_type)
    if start_date and end_date:
        query = query.filter(models.Trip.scheduled_time.between(start_date, end_date))

    # ✅ Execute query
    trips = query.order_by(models.Trip.scheduled_time.asc()).all()

    # ✅ Return simplified data
    return {
        "driver_id": driver_id,
        "total_trips": len(trips),
        "assigned_trips": [
            {
                "trip_id": t.id,
                "delivery_type": t.delivery_type.value if t.delivery_type else None,
                "client_name": t.client_name,
                "pickup_location": t.pickup_location,
                "dropoff_location": t.dropoff_location,
                "scheduled_time": t.scheduled_time,
                "status": t.status.value if t.status else None,
                "priority": t.priority,
                "vehicle_type": t.vehicle_type,
                "distance_km": t.distance_km,
                "cost": t.cost,
            }
            for t in trips
        ]
    }
    