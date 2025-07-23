from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User
from app.schemas import DriverLocationHistoryOut
from app.dependencies import get_current_user

router = APIRouter(prefix="/tracking", tags=["Driver Tracking"])

@router.get("/drivers", response_model=list[DriverLocationHistoryOut])
def get_all_driver_locations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Only allow access for drivers, admins, and super admins
    if current_user.role == "driver":
        # Return only their own location
        if current_user.latitude is None or current_user.longitude is None:
            raise HTTPException(status_code=404, detail="Location not available.")
        return [DriverLocationHistoryOut(
            driver_id=current_user.id,
            latitude=current_user.latitude,
            longitude=current_user.longitude,
            timestamp=current_user.last_location_update
        )]

    elif current_user.role == "admin":
        # Return locations of all drivers in their organization
        drivers = db.query(User).filter(
            User.role == "driver",
            User.client_id == current_user.client_id,
            User.latitude.isnot(None),
            User.longitude.isnot(None)
        ).all()

    elif current_user.role == "super_admin":
        # Return locations of all drivers globally
        drivers = db.query(User).filter(
            User.role == "driver",
            User.latitude.isnot(None),
            User.longitude.isnot(None)
        ).all()

    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access driver locations"
        )

    return [
        DriverLocationHistoryOut(
            driver_id=driver.id,
            latitude=driver.latitude,
            longitude=driver.longitude,
            timestamp=driver.last_location_update
        )
        for driver in drivers
    ]
