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
from app.schemas import TripUpdate, TripPatch, TripResponse, TripAnalyticsResponse,TripCreate
from app.utilites.logging import log_activity
from uuid import UUID
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

    # 🔹 Optional fields: ensure defaults if missing
    trip_data.setdefault("status", "pending")
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

    return db_trip

@router.get("/trips/",response_model=schemas.PaginatedTripsResponse,summary="List all trips with advanced filtering, sorting, and pagination")
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
    skip: int = Query(0, ge=0, description="Number of records to skip for pagination"),
    limit: int = Query(10, ge=1, le=100, description="Number of records to return for pagination"),
    sort_by: Optional[str] = Query("scheduled_time", description="Sort by field name (e.g. 'scheduled_time', 'cost')"),
    sort_order: Optional[str] = Query("desc", description="Sort order: 'asc' or 'desc'"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin"))
):
    query = db.query(models.Trip).filter(models.Trip.organization_id == current_user.organization_id)

    # 🔎 Apply filters
    if status:
        query = query.filter(models.Trip.status.ilike(f"%{status}%"))
    if client_name:
        query = query.filter(models.Trip.client_name.ilike(f"%{client_name}%"))
    if driver_name:
        query = query.filter(models.Trip.driver_name.ilike(f"%{driver_name}%"))
    if delivery_type:
        query = query.filter(models.Trip.delivery_type.ilike(f"%{delivery_type}%"))
    if from_date:
        query = query.filter(models.Trip.scheduled_time >= from_date)
    if to_date:
        query = query.filter(models.Trip.scheduled_time <= to_date)
    if cost_min is not None:
        query = query.filter(models.Trip.cost >= cost_min)
    if cost_max is not None:
        query = query.filter(models.Trip.cost <= cost_max)
    if priority:
        query = query.filter(models.Trip.priority.ilike(f"%{priority}%"))

    # 🔎 Count before pagination (for frontend pagination controls)
    total_count = query.count()

    # 🔎 Sorting
    sort_column = getattr(models.Trip, sort_by, models.Trip.scheduled_time)
    if sort_order.lower() == "desc":
        sort_column = sort_column.desc()
    query = query.order_by(sort_column)

    # 🔎 Apply pagination
    trips = query.offset(skip).limit(limit).all()

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

    # ✅ Validate driver_id if it's in the update payload
    if "driver_id" in update_data:
        driver_id = update_data["driver_id"]
        if driver_id is not None:
            driver = db.query(models.User).filter(
                models.User.id == driver_id,
                models.User.role == "driver",
                models.User.organization_id == current_user.organization_id  # ✅ ensure driver is from same org
            ).first()
            if not driver:
                raise HTTPException(status_code=400, detail=f"Driver with ID {driver_id} not found or not a valid driver")

    # ✅ Apply updates
    for field, value in update_data.items():
        setattr(trip, field, value)

    db.commit()
    db.refresh(trip)
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

    db.delete(trip)
    db.commit()

    # ✅ Log the trip deletion
    log_activity(
        db=db,
        user_id=current_user.id,
        action="trip_deleted",
        details=f"Admin {current_user.name} deleted trip ID {trip.id}",
        trip_id=trip.id
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

    for key, value in trip_data.dict(exclude_unset=True).items():
        setattr(trip, key, value)

    db.commit()
    db.refresh(trip)
    return trip