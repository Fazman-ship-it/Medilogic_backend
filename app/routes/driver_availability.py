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

@router.post("/", status_code=201, response_model=schemas.DriverAvailabilityReplaceResponse)
def set_availability(
    entries: List[schemas.DriverAvailabilityCreate],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if current_user.role != "driver":
        raise HTTPException(status_code=403, detail="Only drivers can set availability.")

    if entries is None:
        raise HTTPException(status_code=400, detail="entries is required")

    # ✅ Validate duplicates in request (same day twice)
    seen_days = set()
    for e in entries:
        if e.day_of_week in seen_days:
            raise HTTPException(status_code=400, detail=f"Duplicate day_of_week in request: {e.day_of_week}")
        seen_days.add(e.day_of_week)

    # ✅ MERGE/UPSERT (no delete)
    for e in entries:
        existing = db.query(models.DriverAvailability).filter(
            models.DriverAvailability.driver_id == current_user.id,
            models.DriverAvailability.day_of_week == e.day_of_week,
        ).first()

        if existing:
            existing.start_time = e.start_time
            existing.end_time = e.end_time
        else:
            db.add(models.DriverAvailability(
                driver_id=current_user.id,
                organization_id=current_user.organization_id,
                day_of_week=e.day_of_week,
                start_time=e.start_time,
                end_time=e.end_time,
            ))

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    saved = db.query(models.DriverAvailability)\
        .filter(models.DriverAvailability.driver_id == current_user.id)\
        .order_by(models.DriverAvailability.day_of_week.asc())\
        .all()

    return {
        "message": "Availability saved successfully.",
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
    
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app import models, schemas
from app.database import get_db
from app.dependencies import get_current_user

from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

@router.delete(
    "/day/{day_of_week}",
    status_code=200,
    response_model=schemas.DriverAvailabilityReplaceResponse
)
def delete_availability_day(
    day_of_week: schemas.WeekDay,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if current_user.role != "driver":
        raise HTTPException(status_code=403, detail="Only drivers can edit availability.")

    # ✅ Delete ONLY that day for this driver
    deleted = db.query(models.DriverAvailability).filter(
        models.DriverAvailability.driver_id == current_user.id,
        models.DriverAvailability.day_of_week == day_of_week,
    ).delete(synchronize_session=False)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    # ✅ Return final saved list (same pattern as POST)
    saved = (
        db.query(models.DriverAvailability)
        .filter(models.DriverAvailability.driver_id == current_user.id)
        .order_by(models.DriverAvailability.day_of_week.asc())
        .all()
    )

    return {
        "message": "Day removed" if deleted else "Day not found",
        "count": len(saved),
        "entries": saved,
    }
    
from typing import List, Dict
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import and_
from app import models, schemas
from app.database import get_db
from app.dependencies import get_current_user

@router.get("/all/grouped", response_model=List[schemas.DriverAvailabilityGroupedOut])
def get_all_driver_availability_grouped(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # Admin-only
    if current_user.role not in ["admin", "superadmin"]:
        raise HTTPException(status_code=403, detail="Admins only.")

    query = db.query(models.DriverAvailability, models.User).join(
        models.User,
        models.User.id == models.DriverAvailability.driver_id
    )

    # Non-superadmin must stay inside their org
    if current_user.role != "superadmin":
        query = query.filter(models.DriverAvailability.organization_id == current_user.organization_id)

    rows = query.order_by(
        models.DriverAvailability.driver_id.asc(),
        models.DriverAvailability.day_of_week.asc()
    ).all()

    grouped: Dict[str, dict] = {}

    for availability_row, driver_user in rows:
        driver_id = str(availability_row.driver_id)

        if driver_id not in grouped:
            grouped[driver_id] = {
                "driver_id": availability_row.driver_id,
                "driver_name": getattr(driver_user, "name", None),
                "availability": [],
            }

        grouped[driver_id]["availability"].append(availability_row)

    return list(grouped.values())