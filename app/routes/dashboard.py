from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional
from app.database import get_db
from app import models
from app.dependencies import get_current_user
from uuid import UUID
from app.utilites.time_utilities import now_utc

router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboards"]
)

from app.models import ShiftAssignment  # Make sure this import is present

@router.get("/driver/{driver_id}")
def get_driver_dashboard(
    driver_id: UUID,
    status: Optional[str] = Query(None),
    delivery_type: Optional[str] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # 🚫 Block if user is a client
    if current_user.role == "client":
        raise HTTPException(status_code=403, detail="Clients are not allowed to access the driver dashboard.")

    # 🚫 Block if driver is accessing another driver's dashboard
    if current_user.role == "driver" and current_user.id != driver_id:
        raise HTTPException(status_code=403, detail="You can only view your own driver dashboard.")

    # ✅ Allow admin or self-driver
    driver_name = current_user.name if current_user.role == "driver" else db.query(models.User).get(driver_id).name

    now = now_utc()
    query = db.query(models.Trip).filter(
        models.Trip.driver_id == driver_id,
        models.Trip.organization_id == current_user.organization_id
    )

    # Apply filters
    if status:
        query = query.filter(models.Trip.status == status)
    if delivery_type:
        query = query.filter(models.Trip.delivery_type == delivery_type)
    if start_date and end_date:
        query = query.filter(models.Trip.scheduled_time.between(start_date, end_date))

    # Get filtered trips (could be all trips or filtered subset)
    trips = query.order_by(models.Trip.scheduled_time.asc()).all()

    # Analytics
    completed = len([t for t in trips if t.status == "completed"])
    in_progress = len([t for t in trips if t.status == "in_progress"])
    cancelled = len([t for t in trips if t.status == "cancelled"])
    total = len(trips)

    # On-time delivery rate (for completed only)
    on_time = [
        t for t in trips if t.status == "completed"
        and t.scheduled_time is not None
        and t.scheduled_time >= t.created_at
    ]
    on_time_rate = f"{(len(on_time)/completed * 100):.1f}%" if completed else "N/A"

    # Most frequent client
    client_names = [t.client_name for t in trips if t.client_name]
    most_frequent_client = max(set(client_names), key=client_names.count) if client_names else "N/A"

    # ✅ Fetch upcoming assigned shifts
    upcoming_shifts = db.query(ShiftAssignment).filter(
        ShiftAssignment.driver_id == driver_id,
        ShiftAssignment.organization_id == current_user.organization_id,
        ShiftAssignment.shift_date >= now.date()
    ).order_by(ShiftAssignment.shift_date.asc()).all()

    shifts_data = [
        {
            "date": s.shift_date,
            "start_time": s.start_time,
            "end_time": s.end_time
        }
        for s in upcoming_shifts
    ]

    return {
        "driver_id": driver_id,
        "driver_name": driver_name,
        "filters": {
            "status": status,
            "delivery_type": delivery_type,
            "start_date": start_date,
            "end_date": end_date
        },
        "trip_summary": {
            "total_trips": total,
            "completed": completed,
            "in_progress": in_progress,
            "cancelled": cancelled,
            "on_time_delivery_rate": on_time_rate,
            "most_frequent_client": most_frequent_client
        },
        "upcoming_trips": [t for t in trips if t.scheduled_time and t.scheduled_time >= now],
        "upcoming_shifts": shifts_data  # ✅ Added section
    }
    
# -----------------------------
# ✅ CLIENT DASHBOARD (ENHANCED)
# -----------------------------
@router.get("/client/{client_id}")
def get_client_dashboard(
    client_id: UUID,
    status: Optional[str] = Query(None),
    delivery_type: Optional[str] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # 🚫 Block if user is a driver
    if current_user.role == "driver":
        raise HTTPException(status_code=403, detail="Drivers are not allowed to access the client dashboard.")

    # 🚫 Block if client is accessing another client's dashboard
    if current_user.role == "client" and current_user.id != client_id:
        raise HTTPException(status_code=403, detail="You can only view your own client dashboard.")

    # ✅ Allow admin or self-client
    client_name = current_user.name if current_user.role == "client" else db.query(models.User).get(client_id).name

    query = db.query(models.Trip).filter(models.Trip.client_name == client_name,models.Trip.organization_id == current_user.organization_id)

    # Optional filters
    if status:
        query = query.filter(models.Trip.status == status)
    if delivery_type:
        query = query.filter(models.Trip.delivery_type == delivery_type)
    if start_date and end_date:
        query = query.filter(models.Trip.scheduled_time.between(start_date, end_date))

    trips = query.all()

    # Trip breakdown
    completed = [t for t in trips if t.status == "completed"]
    in_progress = [t for t in trips if t.status == "in_progress"]
    cancelled = [t for t in trips if t.status == "cancelled"]

    # Most common delivery type
    most_common_delivery_type = None
    if trips:
        all_types = [t.delivery_type for t in trips if t.delivery_type]
        most_common_delivery_type = max(set(all_types), key=all_types.count) if all_types else None

    # Total cost
    total_cost = sum(t.cost for t in trips if t.cost)

    # Delivery speed (in hours)
    delivery_speeds = []
    for t in completed:
        if t.scheduled_time and t.created_at:
            delivery_speeds.append((t.scheduled_time - t.created_at).total_seconds() / 3600)
    avg_delivery_speed = round(sum(delivery_speeds) / len(delivery_speeds), 1) if delivery_speeds else None

    return {
        "client_id": client_id,
        "client_name": client_name,
        "filters": {
            "status": status,
            "delivery_type": delivery_type,
            "start_date": start_date,
            "end_date": end_date
        },
        "trip_count": len(trips),
        "breakdown": {
            "completed": len(completed),
            "in_progress": len(in_progress),
            "cancelled": len(cancelled)
        },
        "analytics": {
            "most_delivery_type": most_common_delivery_type,
            "average_delivery_speed_hrs": avg_delivery_speed,
            "total_spent": f"£{total_cost:,.2f}" if total_cost else "£0.00"
        },
        "trips": trips
    }   
    
    