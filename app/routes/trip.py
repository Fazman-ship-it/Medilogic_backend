# app/routes/trip.py
import pandas as pd
from sklearn.linear_model import LinearRegression
from numpy import mean
import random
from collections import Counter
from app.dependencies import get_current_user
import numpy as np
from sqlalchemy import func
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app import models, schemas
from app.database import get_db
from app import models
from typing import Optional, List
from app.dependencies import require_role
from app.schemas import TripUpdate, TripPatch, TripResponse, TripAnalyticsResponse,TripCreate, TripStatus
from app.utilites.logging import log_activity
from uuid import UUID
from app.models import TripStatus
from app.utilites.time_utilities import to_utc, to_local, now_utc, now_local
# app/routes/trip.py
router = APIRouter()

@router.post("/", response_model=schemas.TripResponse)
def create_trip(
    trip: schemas.TripCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin"))
):
    # ✅ Validate "Others" delivery type
    if trip.delivery_type.lower() == "others" and not trip.custom_delivery_description:
        raise HTTPException(
            status_code=400,
            detail="Custom delivery description is required when delivery type is 'Others'."
        )

    # ✅ Prepare trip data
    trip_data = trip.dict()

    # 🔹 Inject organization_id automatically
    trip_data["organization_id"] = current_user.organization_id

    # 🔹 Optional driver: set None if not provided
    if not trip_data.get("driver_id"):
        trip_data["driver_id"] = None

    # 🔹 Convert schedule_time to UTC before saving
    if "scheduled_time" in trip_data:
        trip_data["scheduled_time"] = to_utc(trip_data["scheduled_time"])

    # Ensure status is valid; default to pending
    status_value = trip_data.get("status", TripStatus.pending.value)
    if status_value not in [s.value for s in TripStatus]:
        raise HTTPException(status_code=400, detail="Invalid trip status")
    trip_data["status"] = status_value

    trip_data.setdefault("compliance_flag", False)
    trip_data.setdefault("priority", "normal")
    trip_data.setdefault("recurrence_rule", "none")

    # ✅ Create and commit trip
    db_trip = models.Trip(**trip_data)
    db.add(db_trip)
    db.commit()
    db.refresh(db_trip)

    # ✅ Log activity for audit
    log_activity(
        db=db,
        user_id=current_user.id,
        action="admin_created_trip",
        trip_id=db_trip.id,
        details=f"Admin {current_user.name} created trip ID {db_trip.id}"
    )

    # 🔹 Optional: convert schedule_time back to local before returning
    db_trip.scheduled_time = to_local(db_trip.scheduled_time)

    return db_trip

@router.get(
    "/trips/",
    response_model=schemas.PaginatedTripsResponse,
    summary="List all trips with advanced filtering, sorting, and pagination"
)
def get_trips(
    status: Optional[str] = Query(None, description="Filter by trip status"),
    priority: Optional[str] = Query(None, description="Filter by priority level (e.g. 'normal', 'urgent', 'stat')"),
    client_name: Optional[str] = Query(None, description="Filter by client name"),
    driver_name: Optional[str] = Query(None, description="Filter by driver name"),
    delivery_type: Optional[str] = Query(None, description="Filter by delivery type"),
    from_date: Optional[datetime] = Query(None, description="Start date for filtering (e.g. 2025-06-10T00:00:00)"),
    to_date: Optional[datetime] = Query(None, description="End date for filtering (e.g. 2025-06-20T23:59:59)"),
    cost_min: Optional[float] = Query(None, description="Minimum cost for filtering"),
    cost_max: Optional[float] = Query(None, description="Maximum cost for filtering"),
    search: Optional[str] = Query(None, description="Generic search across client name, driver name, delivery type, status, and priority"),
    skip: int = Query(0, ge=0, description="Number of records to skip for pagination"),
    limit: int = Query(10, ge=1, le=100, description="Number of records to return for pagination"),
    sort_by: Optional[str] = Query("created_at", description="Sort by field name (e.g. 'created_at', 'scheduled_time', 'cost')"),
    sort_order: Optional[str] = Query("desc", description="Sort order: 'asc' or 'desc'"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin"))
):
    """
    Retrieve trips with advanced filtering, pagination, and sorting.
    Default sorting: newest trips first (created_at DESC).
    """

    # ✅ Base query - scoped by organization and active trips only
    query = db.query(models.Trip).filter(
        models.Trip.organization_id == current_user.organization_id,
        models.Trip.is_deleted == False
    )

    # 🔎 Apply filters
    if status:
        if status not in [s.value for s in TripStatus]:
            raise HTTPException(status_code=400, detail="Invalid trip status")
        query = query.filter(models.Trip.status == status)

    if priority:
        query = query.filter(models.Trip.priority.ilike(f"%{priority}%"))

    if client_name:
        query = query.filter(models.Trip.client_name.ilike(f"%{client_name}%"))

    if driver_name:
        query = query.filter(models.Trip.driver_name.ilike(f"%{driver_name}%"))

    if delivery_type:
        query = query.filter(models.Trip.delivery_type.ilike(f"%{delivery_type}%"))

    if from_date:
        from_date = to_utc(from_date)
        query = query.filter(models.Trip.scheduled_time >= from_date)

    if to_date:
        to_date = to_utc(to_date)
        query = query.filter(models.Trip.scheduled_time <= to_date)

    if cost_min is not None:
        query = query.filter(models.Trip.cost >= cost_min)

    if cost_max is not None:
        query = query.filter(models.Trip.cost <= cost_max)

    # 🔍 Generic search
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (models.Trip.client_name.ilike(search_term)) |
            (models.Trip.driver_name.ilike(search_term)) |
            (models.Trip.delivery_type.ilike(search_term)) |
            (models.Trip.status.ilike(search_term)) |
            (models.Trip.priority.ilike(search_term))
        )

    # 🔢 Count before pagination
    total_count = query.count()

    # ⚙️ Sorting logic (default = newest first by created_at)
    valid_sort_fields = {
        "created_at": models.Trip.created_at,
        "scheduled_time": models.Trip.scheduled_time,
        "cost": models.Trip.cost,
        "distance_km": models.Trip.distance_km,
        "client_name": models.Trip.client_name,
        "driver_name": models.Trip.driver_name,
    }

    sort_column = valid_sort_fields.get(sort_by, models.Trip.created_at)
    if sort_order.lower() == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    # ⏳ Apply pagination
    trips = query.offset(skip).limit(limit).all()

    # 🌍 Convert scheduled_time to local before returning
    for trip in trips:
        if trip.scheduled_time:
            trip.scheduled_time = to_local(trip.scheduled_time)
        if trip.created_at:
            trip.created_at = to_local(trip.created_at)

    return {
        "total": total_count,
        "skip": skip,
        "limit": limit,
        "items": trips
    }

@router.get("/trips/{trip_id}", response_model=schemas.TripResponse)
def get_trip(
    trip_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin"))  # ✅ to access org
):
    # ✅ Scoped by organization
    trip = db.query(models.Trip).filter(
        models.Trip.id == trip_id,
        models.Trip.organization_id == current_user.organization_id
    ).first()

    if not trip:
        raise HTTPException(status_code=404, detail=f"Trip with ID {trip_id} not found")

    return trip   



@router.put("/trips/{trip_id}", response_model=schemas.TripResponse)
def update_trip(
    trip_id: UUID,
    updated_trip: schemas.TripUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin"))  # ✅ Admin-only access
):
    # ✅ Ensure the trip belongs to the current user's organization
    trip = db.query(models.Trip).filter(
        models.Trip.id == trip_id,
        models.Trip.organization_id == current_user.organization_id
    ).first()

    if not trip:
        raise HTTPException(status_code=404, detail=f"Trip with ID {trip_id} not found")

    update_data = updated_trip.model_dump()

    # 🔹 Convert schedule_time to UTC if it's being updated
    if "scheduled_time" in update_data and update_data["scheduled_time"] is not None:
        update_data["scheduled_time"] = to_utc(update_data["scheduled_time"])

    # ✅ Validate status if provided
    if "status" in update_data and update_data["status"] is not None:
        if update_data["status"] not in [s.value for s in TripStatus]:
            raise HTTPException(status_code=400, detail="Invalid trip status")

    # ✅ Validate driver_id if it's in the update payload
    if "driver_id" in update_data:
        driver_id = update_data["driver_id"]
        if driver_id is not None:
            driver = db.query(models.User).filter(
                models.User.id == driver_id,
                models.User.role == "driver",
                models.User.organization_id == current_user.organization_id
            ).first()
            if not driver:
                raise HTTPException(status_code=400, detail=f"Driver with ID {driver_id} not found or not a valid driver")

    # ✅ Apply updates
    for field, value in update_data.items():
        setattr(trip, field, value)

    db.commit()
    db.refresh(trip)

    # 🔹 Convert schedule_time back to local before returning
    trip.scheduled_time = to_local(trip.scheduled_time)

    return trip


@router.delete("/trips/{trip_id}", status_code=200)
def delete_trip(
    trip_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin"))  # ✅ capture current user
):
    # ✅ Only delete if trip belongs to current user's organization
    trip = db.query(models.Trip).filter(
        models.Trip.id == trip_id,
        models.Trip.organization_id == current_user.organization_id
    ).first()

    if not trip:
        raise HTTPException(status_code=404, detail=f"Trip with ID {trip_id} not found")

    # ✅ Soft delete instead of hard delete
    trip.is_deleted = True  
    db.add(trip)
    db.commit()

    # ✅ Log the trip deletion (still references trip_id safely)
    log_activity(
        db=db,
        user_id=current_user.id,
        action="trip_deleted",
        details=f"Admin {current_user.name} deleted trip ID {trip.id}",
        trip_id=trip.id  # still valid since we soft deleted
    )

    return {"message": f"Trip with ID {trip_id} has been deleted successfully"}



@router.patch("/trips/{trip_id}", response_model=schemas.TripResponse)
def partial_update_trip(
    trip_id: UUID,
    trip_data: schemas.TripPatch,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin"))  # ✅ needed to access org
):
    # ✅ Only allow patching if trip belongs to current user's organization
    trip = db.query(models.Trip).filter(
        models.Trip.id == trip_id,
        models.Trip.organization_id == current_user.organization_id
    ).first()

    if not trip:
        raise HTTPException(status_code=404, detail=f"Trip with ID {trip_id} not found")

    patch_data = trip_data.dict(exclude_unset=True)

    # 🔹 Convert schedule_time to UTC if included
    if "scheduled_time" in patch_data and patch_data["scheduled_time"] is not None:
        patch_data["scheduled_time"] = to_utc(patch_data["scheduled_time"])

    # ✅ Validate status if provided
    if "status" in patch_data and patch_data["status"] is not None:
        if patch_data["status"] not in [s.value for s in TripStatus]:
            raise HTTPException(status_code=400, detail="Invalid trip status")

    # Apply patch
    for key, value in patch_data.items():
        setattr(trip, key, value)

    db.commit()
    db.refresh(trip)

    # 🔹 Convert schedule_time back to local before returning
    trip.scheduled_time = to_local(trip.scheduled_time)

    return trip