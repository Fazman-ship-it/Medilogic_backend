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

from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from app import models, schemas
from app.database import get_db
from app.dependencies import get_current_user

@router.post("/", status_code=201, response_model=schemas.DriverAvailabilityReplaceResponse)
def set_availability(
    entries: List[schemas.DriverAvailabilityCreate],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if current_user.role != "driver":
        raise HTTPException(status_code=403, detail="Only drivers can set availability.")

    # ✅ must send full list (or empty list to clear all)
    if entries is None:
        raise HTTPException(status_code=400, detail="entries is required")

    # ✅ Validate duplicates in request (same day twice)
    seen_days = set()
    for e in entries:
        if e.day_of_week in seen_days:
            raise HTTPException(status_code=400, detail=f"Duplicate day_of_week in request: {e.day_of_week}")
        seen_days.add(e.day_of_week)

    # ✅ Delete existing rows FIRST (full replace)
    db.query(models.DriverAvailability)\
      .filter(models.DriverAvailability.driver_id == current_user.id)\
      .delete(synchronize_session=False)

    # ✅ Insert new rows
    objs = [
        models.DriverAvailability(
            driver_id=current_user.id,
            organization_id=current_user.organization_id,
            day_of_week=e.day_of_week,   # enum handled by schema
            start_time=e.start_time,
            end_time=e.end_time,
        )
        for e in entries
    ]

    if objs:
        db.add_all(objs)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    # ✅ Return what’s now saved (helps frontend immediately)
    saved = db.query(models.DriverAvailability)\
        .filter(models.DriverAvailability.driver_id == current_user.id)\
        .order_by(models.DriverAvailability.day_of_week.asc())\
        .all()

    return {
        "message": "Availability replaced successfully.",
        "count": len(saved),
        "entries": saved,
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