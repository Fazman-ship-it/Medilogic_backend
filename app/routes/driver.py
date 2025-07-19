from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app import models
from app.database import get_db
from app.dependencies import get_current_user
from pydantic import BaseModel
from app.utilites.logging import log_activity

router = APIRouter(
    prefix="/drivers",
    tags=["Drivers"]
)

class LocationUpdate(BaseModel):
    latitude: float
    longitude: float

@router.patch("/location")
def update_driver_location(
    location: LocationUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role != "driver":
        raise HTTPException(status_code=403, detail="Only drivers can update location.")

    current_user.latitude = location.latitude
    current_user.longitude = location.longitude
    db.commit()

    # ✅ Log location update
    log_activity(
        db=db,
        user_id=current_user.id,
        action="driver_location_updated",
        details=f"Driver {current_user.name} updated location to ({location.latitude}, {location.longitude})"
    )

    return {"message": "Driver location updated successfully."}