# app/routes/optimizer.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app import models, schemas
from app.dependencies import require_role
from app.utilites.logging import log_activity
import joblib
import datetime
import pandas as pd
from app.utilites.geolocation import haversine_distance
import os
from geopy.distance import geodesic

router = APIRouter(
    prefix="/optimizer",
    tags=["AI Optimization"]
)

# ✅ Load the trained model once — safer path
MODEL_PATH = os.path.join("models", "scheduler_optimizer_model.pkl")
model = joblib.load(MODEL_PATH)


@router.post("/optimize-scheduling", response_model=schemas.OptimizerResponse)
def optimize_trip_scheduling(
    data: schemas.OptimizerRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin"))
):
    """
    AI-powered driver recommendation and auto-trip creation.
    """
    # ✅ Step 1: Fetch all eligible drivers with location
    drivers = db.query(models.User).filter(
        models.User.role == "driver",
        models.User.organization_id == current_user.organization_id,
        models.User.latitude.isnot(None),
        models.User.longitude.isnot(None)
    ).all()

    if not drivers:
        raise HTTPException(status_code=404, detail="No available drivers with location data.")

    driver_predictions = []

    for driver in drivers:
        # ✅ Step 2: Compute distance to pickup location
        driver_location = (driver.latitude, driver.longitude)
        pickup_location = (data.pickup_lat, data.pickup_lon)
        distance_km = geodesic(driver_location, pickup_location).km

        # ✅ Step 3: Create DataFrame for prediction
        df = pd.DataFrame([{
            "delivery_type": data.delivery_type,
            "priority_score": data.priority_score,
            "distance_to_pickup_km": distance_km,
            "driver_rating": driver.rating or 4.0,  # Default if missing
        }])

        df = pd.get_dummies(df)

        # ✅ Ensure all expected columns exist
        for col in model.feature_names_in_:
            if col not in df.columns:
                df[col] = 0

        df = df[model.feature_names_in_]

        predicted_score = model.predict(df)[0]
        driver_predictions.append((driver, distance_km, predicted_score))

    # ✅ Step 4: Rank drivers by predicted score
    driver_predictions.sort(key=lambda x: x[2], reverse=True)

    if not driver_predictions:
        raise HTTPException(status_code=500, detail="Unable to make a driver prediction.")

    best_driver, best_distance, best_score = driver_predictions[0]

    # ✅ Step 5: Auto-create a trip
    trip = models.Trip(
        client_id=data.client_id,
        driver_id=best_driver.id,
        delivery_type=data.delivery_type,
        pickup_location=data.pickup_address,
        dropoff_location=data.dropoff_address,
        distance_km=best_distance,
        status="assigned",
        scheduled_time=datetime.datetime.utcnow() + datetime.timedelta(minutes=10),
        cost=data.estimated_cost,
        priority=data.priority,
    )

    db.add(trip)
    db.commit()
    db.refresh(trip)

    # ✅ Step 6: Log activity
    log_activity(
        db=db,
        user_id=current_user.id,
        action="AI-Optimized Trip Assigned",
        details=f"Driver {best_driver.name} (ID: {best_driver.id}) assigned via optimizer",
        trip_id=trip.id
    )

    # ✅ Step 7: Return full response
    return schemas.OptimizerResponse(
        trip_id=trip.id,
        assigned_driver_id=best_driver.id,
        assigned_driver_name=best_driver.name,
        scheduled_time=trip.scheduled_time,
        predicted_score=round(best_score, 2),
        top_3_recommendations=[
            schemas.DriverRecommendation(
                driver_id=d.id,
                driver_name=d.name,
                distance_km=round(dist, 2),
                predicted_score=round(score, 2)
            )
            for d, dist, score in driver_predictions[:3]
        ]
    ) 