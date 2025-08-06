from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime,date
from app.database import get_db
from app import models, schemas
from app.dependencies import get_current_user
from app.enums import DeliveryType  # ✅ Import the enum
from typing import List,Optional
from fastapi import Query
from app.utilites.logging import log_activity
from uuid import UUID

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
        scheduled_time=trip_data.scheduled_time,
        pickup_location=trip_data.pickup_location,
        dropoff_location=trip_data.dropoff_location,
        distance_km=trip_data.distance_km,
        priority=trip_data.priority,
        status="pending",
        driver_id=None,
        cost=None,
        created_at=datetime.utcnow(),
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
    if current_user.role != "client":
        raise HTTPException(status_code=403, detail="Access denied")

    query = db.query(models.Trip).filter(models.Trip.client_id == current_user.id)

    if status:
        query = query.filter(models.Trip.status == status)

    if delivery_type:
        query = query.filter(models.Trip.delivery_type == delivery_type)

    if start_date:
        query = query.filter(models.Trip.scheduled_time >= start_date)

    if end_date:
        query = query.filter(models.Trip.scheduled_time <= end_date)

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
