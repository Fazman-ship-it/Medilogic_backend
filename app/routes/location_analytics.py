from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from app.dependencies import get_db, get_current_user
from app import models
from datetime import datetime
from math import radians, cos, sin, asin, sqrt
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
from app.database import get_db
from app.schemas import DriverLocationHistoryOut
from app.models import User, DriverLocationHistory
from sqlalchemy import func
import pickle
import numpy as np
from geopy.distance import geodesic
from pandas import DataFrame
import pandas as pd
from uuid import UUID


router = APIRouter()

def haversine(lat1, lon1, lat2, lon2):
    R = 6371  # Earth radius in km
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    return R * c

@router.get("/location/history/summary")
def location_history_summary(
    driver_id: UUID,
    start: datetime = Query(...),
    end: datetime = Query(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Ensure only same org can access
    driver = db.query(models.User).filter(
        models.User.id == driver_id,
        models.User.organization_id == current_user.organization_id
    ).first()

    if not driver:
        return {"error": "Driver not found in your organization"}

    locations = db.query(models.DriverLocationHistory).filter(
        models.DriverLocationHistory.driver_id == driver_id,
        models.DriverLocationHistory.timestamp >= start,
        models.DriverLocationHistory.timestamp <= end
    ).order_by(models.DriverLocationHistory.timestamp.asc()).all()

    total_distance = 0.0
    prev = None
    path = []
    idle_points = []
    unusual_jumps = []

    for loc in locations:
        current_point = {
            "latitude": loc.latitude,
            "longitude": loc.longitude,
            "timestamp": loc.timestamp.isoformat()
        }
        path.append(current_point)

        # Calculate total distance
        if prev:
            dist = haversine(prev.latitude, prev.longitude, loc.latitude, loc.longitude)
            total_distance += dist

            # Detect unusual jump (>2km between updates)
            if dist > 2:
                unusual_jumps.append({
                    "from": {
                        "latitude": prev.latitude,
                        "longitude": prev.longitude,
                        "timestamp": prev.timestamp.isoformat()
                    },
                    "to": current_point,
                    "distance_km": round(dist, 2)
                })

            # Detect idle (same location for over 5 minutes)
            if round(prev.latitude, 5) == round(loc.latitude, 5) and round(prev.longitude, 5) == round(loc.longitude, 5):
                idle_duration = (loc.timestamp - prev.timestamp).total_seconds() / 60
                if idle_duration >= 5:
                    idle_points.append({
                        "location": {
                            "latitude": loc.latitude,
                            "longitude": loc.longitude
                        },
                        "start": prev.timestamp.isoformat(),
                        "end": loc.timestamp.isoformat(),
                        "duration_minutes": round(idle_duration, 1)
                    })

        prev = loc

    return {
        "driver_id": driver_id,
        "driver_name": driver.name,
        "total_distance_km": round(total_distance, 2),
        "point_count": len(path),
        "path": path,
        "idle_periods": idle_points,
        "unusual_movements": unusual_jumps
    }
    
@router.get("/driver/{driver_id}/tracking-history", response_model=list[DriverLocationHistoryOut])
def get_tracking_history(
    driver_id: UUID,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # Get the target driver
    target_driver = db.query(models.User).filter(
        models.User.id == driver_id,
        models.User.role == "driver"
    ).first()

    if not target_driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    # PERMISSION CHECK:
    if current_user.role == "driver":
        if current_user.id != driver_id:
            raise HTTPException(status_code=403, detail="Drivers can only access their own data.")
    elif current_user.role == "admin":
        if current_user.organization_id != target_driver.organization_id:
            raise HTTPException(status_code=403, detail="Admins can only access drivers in their organization.")
    elif current_user.role != "super_admin":
        raise HTTPException(status_code=403, detail="Unauthorized")

    # Query tracking history
    query = db.query(models.DriverLocationHistory).filter(
        models.DriverLocationHistory.driver_id == driver_id
    )

    if start_date:
        query = query.filter(models.DriverLocationHistory.timestamp >= start_date)
    if end_date:
        query = query.filter(models.DriverLocationHistory.timestamp <= end_date)

    return query.order_by(models.DriverLocationHistory.timestamp).all()


@router.get("/heatmap")
def get_heatmap_data(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    driver_id: Optional[UUID] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Build base query
    query = db.query(
        DriverLocationHistory.latitude,
        DriverLocationHistory.longitude,
        func.count().label("count")
    )

    # Apply filters
    if start_date:
        query = query.filter(DriverLocationHistory.timestamp >= start_date)
    if end_date:
        query = query.filter(DriverLocationHistory.timestamp <= end_date)
    if driver_id:
        query = query.filter(DriverLocationHistory.driver_id == driver_id)

    # Access control (multi-tenant)
    if current_user.role == "driver":
        query = query.filter(DriverLocationHistory.driver_id == current_user.id)
    elif current_user.role == "admin":
        driver_ids = db.query(User.id).filter(User.organization_id == current_user.organization_id, User.role == "driver")
        query = query.filter(DriverLocationHistory.driver_id.in_(driver_ids))
    elif current_user.role != "super_admin":
        raise HTTPException(status_code=403, detail="Access denied")

    # Group by location for heatmap
    query = query.group_by(
        DriverLocationHistory.latitude,
        DriverLocationHistory.longitude
    )

    results = query.all()

    # Format response
    return [
        {
            "latitude": lat,
            "longitude": lng,
            "count": count
        }
        for lat, lng, count in results
    ]


# Load the model once when the router is loaded
try:
    with open("next_location_model_v2.pkl", "rb") as f:
        next_location_model = pickle.load(f)
except Exception as e:
    next_location_model = None
    print("❌ Could not load prediction model:", e)


@router.get("/predict-next-location")
def predict_next_location(
    driver_id: UUID,
    db: Session = Depends(get_db)
):
    if not next_location_model:
        raise HTTPException(status_code=500, detail="Model not loaded")

    # Get last known location history for this driver
    locations = (
        db.query(DriverLocationHistory)
        .filter(DriverLocationHistory.driver_id == driver_id)
        .order_by(DriverLocationHistory.timestamp.desc())
        .limit(1)
        .all()
    )

    if not locations:
        raise HTTPException(status_code=404, detail="No location data found for this driver")

    last_location = locations[0]

    # Example: using latitude, longitude, hour as features
    hour_of_day = last_location.timestamp.hour
    input_features = np.array([[last_location.latitude, last_location.longitude, hour_of_day]])

    predicted = next_location_model.predict(input_features)[0]
    predicted_lat, predicted_lng = predicted

    return {
        "driver_id": driver_id,
        "predicted_latitude": predicted_lat,
        "predicted_longitude": predicted_lng,
        "based_on_time": hour_of_day,
        "timestamp_used": last_location.timestamp,
    }
    
from fastapi import Depends
from app.dependencies import get_current_user  # Assumes you have this
from app.models import Trip, DriverLocationHistory
from geopy.distance import geodesic
import numpy as np
import pandas as pd

@router.get("/check-anomaly")
def check_driver_deviation(
    driver_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)  # 🛡️ Extract user/org info from token
):
    if not next_location_model:
        raise HTTPException(status_code=500, detail="Model not loaded")

    # Step 1: Get the latest location
    location = (
        db.query(DriverLocationHistory)
        .filter(DriverLocationHistory.driver_id == driver_id)
        .order_by(DriverLocationHistory.timestamp.desc())
        .first()
    )

    if not location:
        raise HTTPException(status_code=404, detail="No recent location found")

    # Step 2: Get latest trip for this driver
    trip = (
        db.query(Trip)
        .filter(Trip.driver_id == driver_id)
        .order_by(Trip.scheduled_time.desc())
        .first()
    )

    if not trip:
        raise HTTPException(status_code=404, detail="No trip data found for this driver")

    # 🛡️ Step 3: Multi-tenant check
    if trip.organization_id != current_user["organization_id"]:
        raise HTTPException(status_code=403, detail="Unauthorized access to this driver’s data")

    # Step 4: Prepare features
    hour = location.timestamp.hour
    day_of_week = location.timestamp.weekday()
    delivery_type = pd.Series([trip.delivery_type]).astype("category").cat.codes[0]
    

    input_features = np.array([[location.latitude, location.longitude, hour, day_of_week, driver_id, delivery_type]])
    predicted = next_location_model.predict(input_features)[0]

    actual_coords = (location.latitude, location.longitude)
    predicted_coords = (predicted[0], predicted[1])
    distance_km = geodesic(actual_coords, predicted_coords).km

    anomaly = distance_km > 10

    return {
        "driver_id": driver_id,
        "actual_location": actual_coords,
        "predicted_location": predicted_coords,
        "distance_km": round(distance_km, 2),
        "is_anomaly": anomaly
    }
    
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from geopy.distance import geodesic
import numpy as np
import pandas as pd
from app.database import get_db
from app.dependencies import get_current_user
from app.models import DriverLocationHistory, Trip



@router.get("/top-off-route-drivers")
def top_off_route_drivers(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    if not next_location_model:
        raise HTTPException(status_code=500, detail="Model not loaded")

    # Step 1: Get the latest location per driver in current org
    subquery = (
        db.query(
            DriverLocationHistory.driver_id,
            db.func.max(DriverLocationHistory.timestamp).label("latest_time")
        )
        .group_by(DriverLocationHistory.driver_id)
        .subquery()
    )

    latest_locations = (
        db.query(DriverLocationHistory)
        .join(
            subquery,
            (DriverLocationHistory.driver_id == subquery.c.driver_id) &
            (DriverLocationHistory.timestamp == subquery.c.latest_time)
        )
        .all()
    )

    results = []

    for location in latest_locations:
        # Get trip for multi-tenant filtering and feature input
        trip = (
            db.query(Trip)
            .filter(Trip.driver_id == location.driver_id)
            .order_by(Trip.scheduled_time.desc())
            .first()
        )

        if not trip:
            continue  # Skip if no trip found

        if trip.organization_id != current_user["organization_id"]:
            continue  # 🚫 Skip drivers from another org

        try:
            # Build input features
            hour = location.timestamp.hour
            day_of_week = location.timestamp.weekday()
            delivery_type = pd.Series([trip.delivery_type]).astype("category").cat.codes[0]
            

            input_features = np.array([[location.latitude, location.longitude, hour, day_of_week, location.driver_id, delivery_type]])
            predicted = next_location_model.predict(input_features)[0]

            actual_coords = (location.latitude, location.longitude)
            predicted_coords = (predicted[0], predicted[1])
            distance_km = geodesic(actual_coords, predicted_coords).km

            results.append({
                "driver_id": location.driver_id,
                "actual_location": actual_coords,
                "predicted_location": predicted_coords,
                "distance_km": round(distance_km, 2)
            })
        except Exception:
            continue  # Skip any prediction failures

    # Sort and return top 5
    sorted_results = sorted(results, key=lambda x: x["distance_km"], reverse=True)
    return sorted_results[:5]