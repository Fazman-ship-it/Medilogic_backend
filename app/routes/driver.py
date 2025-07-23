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
router = APIRouter(
    prefix="/drivers",
    tags=["Drivers"]
)

from app.models import DriverLocationHistory

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
    current_user.last_location_update = datetime.utcnow()

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
    driver_id: int,
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
    driver_id: int,
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
    