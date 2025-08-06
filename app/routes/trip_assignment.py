# app/routes/trip_assignment.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app import models, schemas
from app.database import get_db
from app.dependencies import get_current_user, require_role
from app.utilites.logging import log_activity
from uuid import UUID
router = APIRouter(
    prefix="/assign-driver",
    tags=["Trip Assignment"]
)


@router.post("/{trip_id}")
def assign_driver_to_trip(
    trip_id: UUID,
    data: schemas.AssignDriverRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin"))  # Only admin can access
):
    trip = db.query(models.Trip).filter(models.Trip.id == trip_id, models.Trip.organization_id == current_user.organization_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    if trip.driver_id:
        raise HTTPException(status_code=400, detail="Trip already has a driver assigned")

    driver = db.query(models.User).filter(models.User.id == data.driver_id, models.User.role == "driver").first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    trip.driver_id = data.driver_id
    trip.status = "assigned"
    db.commit()
    db.refresh(trip)

    # ✅ Log the activity using your existing log_activity function
    log_activity(
        db=db,
        user_id=current_user.id,
        action="assign_driver",
        details=f"Assigned driver {driver.id} to trip {trip.id}",
        trip_id=trip.id
    )

    return {"message": f"Driver {driver.id} assigned to trip {trip.id}"}

@router.get("/unassigned", response_model=list[schemas.TripResponse])
def list_unassigned_trips(
    db: Session = Depends(get_db),
    _: models.User = Depends(require_role("admin"))
):
    trips = db.query(models.Trip).filter(
        models.Trip.driver_id == None,
        models.Trip.organization_id == _.organization_id  # ✅ Multi-tenant filter
    ).all()
    return trips

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.utilites.smart_scheduler import suggest_pickup_time_window

router = APIRouter(
    prefix="/smart-scheduler",
    tags=["AI Optimization"]
)

@router.get("/suggest-pickup")
def get_suggested_pickup_time(
    delivery_type: str = Query(...),
    distance_km: float = Query(...),
    cost: float = Query(0),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin"))
):
    """
    Suggest the best pickup window for a delivery using AI model.
    """
    result = suggest_pickup_time_window(
        delivery_type=delivery_type,
        distance_km=distance_km,
        cost=cost
    )
    return result