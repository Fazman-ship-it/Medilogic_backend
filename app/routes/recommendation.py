from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencies import require_role
from app.utilites.driver_recommendation import recommend_nearest_drivers
from app import models
from app.utilites.logging import log_activity

router = APIRouter(
    prefix="/recommendation",
    tags=["AI Optimization"]
)

@router.get("/recommend")
def recommend_drivers(
    pickup_lat: float = Query(..., description="Pickup latitude"),
    pickup_lon: float = Query(..., description="Pickup longitude"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin"))
):
    """
    Recommend nearest available drivers to the pickup location.
    """
    recommendations = recommend_nearest_drivers(
        db=db,
        pickup_lat=pickup_lat,
        pickup_lon=pickup_lon,
        organization_id=current_user.organization_id  # ✅ multi-tenant scoped
    )

    # ✅ Log this action
    log_activity(
        db=db,
        user_id=current_user.id,
        action="driver_recommendation_requested",
        details=f"Admin {current_user.name} requested driver recommendation for pickup at ({pickup_lat}, {pickup_lon})"
    )

    return [
        {
            "driver_id": driver.id,
            "name": driver.full_name,
            "distance_km": round(distance, 2),
            "latitude": driver.latitude,
            "longitude": driver.longitude,
        }
        for driver, distance in recommendations
    ]

