from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app import models, schemas
from app.dependencies import get_db
from app.dependencies import get_current_user
from datetime import time

router = APIRouter(
    prefix="/availability",
    tags=["Driver Availability"]
)

# 🚚 Drivers: Set their availability
@router.post("/", status_code=201)
def set_availability(
    entries: List[schemas.DriverAvailabilityCreate],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role != "driver":
        raise HTTPException(status_code=403, detail="Only drivers can set availability.")

    # Clear old entries
    db.query(models.DriverAvailability).filter_by(driver_id=current_user.id).delete()

    # Add new entries
    for entry in entries:
        db.add(models.DriverAvailability(
            driver_id=current_user.id,
            organization_id=current_user.organization_id,
            day_of_week=entry.day_of_week,
            start_time=entry.start_time,
            end_time=entry.end_time
        ))

    db.commit()
    return {"message": "Availability updated successfully."}


# ✅ Drivers: View their own availability
@router.get("/me", response_model=List[schemas.DriverAvailabilityOut])
def get_my_availability(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role != "driver":
        raise HTTPException(status_code=403, detail="Only drivers can view availability.")

    entries = db.query(models.DriverAvailability).filter_by(driver_id=current_user.id).all()
    return entries


# 🛡 Admins: View availability of all drivers in their organization
@router.get("/all", response_model=List[schemas.DriverAvailabilityOut])
def get_all_driver_availability(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role not in ["admin", "superadmin"]:
        raise HTTPException(status_code=403, detail="Admins only.")

    query = db.query(models.DriverAvailability)

    if current_user.role != "superadmin":
        query = query.filter(models.DriverAvailability.organization_id == current_user.organization_id)

    return query.all()