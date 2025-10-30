from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime,date,time
from app.database import get_db
from app import models, schemas
from app.dependencies import get_current_user
from app.enums import DeliveryType  # ✅ Import the enum
from typing import List,Optional
from fastapi import Query
from app.utilites.logging import log_activity
from uuid import UUID
from app.utilites.time_utilities import to_utc, now_utc  # 🔹 Import time utilities

router = APIRouter(
    prefix="/client/trips",
    tags=["Client Trips"]
)

# ⬇️ In client trip booking route

@router.post("/", response_model=schemas.TripClientResponse)
def create_trip_as_client(
    trip_data: schemas.TripCreateClient,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role != "client":
        raise HTTPException(status_code=403, detail="Only clients can schedule trips")

    if trip_data.delivery_type == DeliveryType.other and not trip_data.custom_delivery_description:
        raise HTTPException(
            status_code=400,
            detail="Please provide a custom delivery description when delivery_type is 'other'."
        )

    trip = models.Trip(
        client_name=current_user.name,
        delivery_type=trip_data.delivery_type,
        custom_delivery_description=trip_data.custom_delivery_description,
        scheduled_time=to_utc(trip_data.scheduled_time),  # 🔹 convert to UTC
        pickup_location=trip_data.pickup_location,
        dropoff_location=trip_data.dropoff_location,
        distance_km=trip_data.distance_km,
        priority=trip_data.priority,
        status="pending",
        driver_id=None,
        cost=None,
        created_at=now_utc(),  # 🔹 UTC-aware creation time
        organization_id=current_user.organization_id,
        client_id=current_user.id
    )

    db.add(trip)
    db.commit()
    db.refresh(trip)

    # ✅ Add audit log entry
    log_activity(
        db=db,
        user_id=current_user.id,
        action="trip_booked",
        details=f"Client {current_user.name} booked a new trip ID {trip.id}",
        trip_id=trip.id
    )

    return trip


@router.get("/", response_model=List[schemas.TripResponse])
def get_client_trips(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    status: Optional[str] = Query(None),
    delivery_type: Optional[DeliveryType] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
):
    """
    Retrieve trips for:
    - Clients → only their own trips
    - Admins → all client trips under their organization
    """

    # ✅ Role-based filtering
    if current_user.role == "client":
        query = db.query(models.Trip).filter(models.Trip.client_id == current_user.id)
    elif current_user.role == "admin":
        query = db.query(models.Trip).filter(
            models.Trip.organization_id == current_user.organization_id
        )
    else:
        raise HTTPException(status_code=403, detail="Access denied")

    # ✅ Optional filters
    if status:
        query = query.filter(models.Trip.status == status)

    if delivery_type:
        query = query.filter(models.Trip.delivery_type == delivery_type)

    # ✅ Convert start_date and end_date to UTC datetimes
    if start_date:
        start_dt = to_utc(datetime.combine(start_date, time.min))
        query = query.filter(models.Trip.scheduled_time >= start_dt)

    if end_date:
        end_dt = to_utc(datetime.combine(end_date, time.max))
        query = query.filter(models.Trip.scheduled_time <= end_dt)

    # ✅ Sort by most recent scheduled_time
    return query.order_by(models.Trip.scheduled_time.desc()).all()
    
@router.patch("/{trip_id}/status")
def update_trip_status(
    trip_id: UUID,
    status_update: schemas.TripClientStatusUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role != "client":
        raise HTTPException(status_code=403, detail="Only clients can update trip status")

    trip = db.query(models.Trip).filter(
        models.Trip.id == trip_id,
        models.Trip.client_id == current_user.id
    ).first()

    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    trip.status = status_update.status
    db.commit()
    db.refresh(trip)

    # ✅ Log this trip status update
    log_activity(
        db=db,
        user_id=current_user.id,
        action="trip_status_updated",
        details=f"Client {current_user.name} updated trip {trip.id} status to {trip.status}",
        trip_id=trip.id
    )

    return {"message": f"Trip {trip.id} status updated to {trip.status}"}
    
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, case
from datetime import datetime
from uuid import UUID
from typing import List, Optional
from app import models, schemas
from app.database import get_db
from app.dependencies import get_current_user
from app.utilites.time_utilities import to_utc, now_utc,to_local


@router.get(
    "/assigned",
    response_model=schemas.ClientAssignedTripsResponse,
    summary="Get trips assigned to the current client or their organization"
)
def get_assigned_client_trips(
    status: Optional[str] = Query(None, description="Filter by trip status"),
    delivery_type: Optional[str] = Query(None, description="Filter by delivery type"),
    start_date: Optional[datetime] = Query(None, description="Start of date range"),
    end_date: Optional[datetime] = Query(None, description="End of date range"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Retrieve all trips assigned to the logged-in client.
    - Clients see only their own trips.
    - Admins/managers see all client trips within their organization.
    - Sorted by most recent trips first.
    """

    # ✅ Access control
    if current_user.role == "driver":
        raise HTTPException(status_code=403, detail="Drivers cannot view client trips.")

    # ✅ Base query
    query = db.query(models.Trip).filter(
        models.Trip.organization_id == current_user.organization_id
    )

    if current_user.role == "client":
        query = query.filter(models.Trip.client_id == current_user.id)

    # ✅ Apply filters
    if status:
        query = query.filter(models.Trip.status.ilike(f"%{status}%"))
    if delivery_type:
        query = query.filter(models.Trip.delivery_type.ilike(f"%{delivery_type}%"))
    if start_date and end_date:
        query = query.filter(models.Trip.scheduled_time.between(start_date, end_date))

    # ✅ Sort by most recent
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

    # ✅ Structure response for frontend clarity
    return {
        "client_id": current_user.id,
        "total_trips": len(trips),
        "assigned_trips": [
            {
                "trip_id": t.id,
                "trip_label": f"{t.driver_name or 'Unassigned'} — {(
                    t.custom_delivery_description
                    if t.delivery_type and str(t.delivery_type).lower() == 'others'
                    else (t.delivery_type or 'Unspecified')
                )}",
                "driver_name": t.driver_name,
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
                "custom_delivery_description": t.custom_delivery_description,
            }
            for t in trips
        ]
    }