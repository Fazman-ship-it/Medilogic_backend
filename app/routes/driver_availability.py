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
from fastapi import HTTPException
from sqlalchemy import func

@router.post("/", status_code=201)
def set_availability(
    entries: List[schemas.DriverAvailabilityCreate],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role != "driver":
        raise HTTPException(status_code=403, detail="Only drivers can set availability.")

    # ✅ Debug: confirm we received entries
    print("SET AVAILABILITY user_id:", current_user.id)
    print("SET AVAILABILITY entries_count:", len(entries))

    # Clear old entries (safer for bulk delete)
    db.query(models.DriverAvailability)\
      .filter(models.DriverAvailability.driver_id == current_user.id)\
      .delete(synchronize_session=False)

    # Add new entries
    objs = []
    for entry in entries:
        obj = models.DriverAvailability(
            driver_id=current_user.id,
            organization_id=current_user.organization_id,
            day_of_week=entry.day_of_week,
            start_time=entry.start_time,
            end_time=entry.end_time
        )
        objs.append(obj)

    db.add_all(objs)

    # ✅ Flush first so we know rows exist before commit
    db.flush()

    # ✅ Debug: confirm rows exist inside this transaction
    in_tx_count = db.query(func.count(models.DriverAvailability.id))\
        .filter(models.DriverAvailability.driver_id == current_user.id)\
        .scalar()
    print("IN-TRANSACTION count:", in_tx_count)

    db.commit()

    # ✅ Debug: confirm after commit too
    after_commit_count = db.query(func.count(models.DriverAvailability.id))\
        .filter(models.DriverAvailability.driver_id == current_user.id)\
        .scalar()
    print("AFTER COMMIT count:", after_commit_count)

    return {
        "message": "Availability updated successfully.",
        "saved": len(entries),
        "after_commit_count": after_commit_count,
        "user_id": str(current_user.id),
    }

@router.get("/me", response_model=List[schemas.DriverAvailabilityOut])
def get_my_availability(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    print("GET MY AVAILABILITY user_id:", current_user.id)

    entries = db.query(models.DriverAvailability)\
        .filter(models.DriverAvailability.driver_id == current_user.id)\
        .all()

    print("GET MY AVAILABILITY count:", len(entries))
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