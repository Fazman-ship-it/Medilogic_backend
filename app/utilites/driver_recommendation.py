# app/ai/driver_recommendation.py

from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from app import models
from app.utilites.geolocation import haversine_distance

def recommend_nearest_drivers(
    db: Session,
    pickup_lat: float,
    pickup_lon: float,
    limit: int = 5,
    delivery_type: Optional[str] = None,
    current_user: models.User = None  # ✅ Accept current_user to access org
) -> List[Tuple[models.User, float]]:
    """
    Recommend nearest available drivers to a pickup location.
    Optionally filters by delivery type (e.g., clinical waste, samples).
    Returns a list of tuples: (driver, distance_km)
    """
    query = db.query(models.User).filter(models.User.role == "driver")

    # ✅ Multi-tenant: Only drivers in the same organization
    if current_user:
        query = query.filter(models.User.organization_id == current_user.organization_id)

    # Only include drivers with known location
    query = query.filter(models.User.latitude.isnot(None), models.User.longitude.isnot(None))

    # Optionally filter by driver delivery specialization (if implemented)
    if delivery_type:
        query = query.filter(models.User.delivery_type == delivery_type)  # Only if you store this

    drivers = query.all()

    recommendations = []
    for driver in drivers:
        distance = haversine_distance(pickup_lat, pickup_lon, driver.latitude, driver.longitude)
        recommendations.append((driver, distance))

    # Sort by distance and return top N
    recommendations.sort(key=lambda x: x[1])
    return recommendations[:limit]