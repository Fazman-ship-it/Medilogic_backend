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
import os
import datetime
import joblib
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app import models, schemas
from app.dependencies import get_db, require_role

router = APIRouter(
    prefix="/optimizer",
    tags=["AI Optimization"]
)

MODELS_DIR = "models"
os.makedirs(MODELS_DIR, exist_ok=True)

MIN_TRAINING_SAMPLES = 20  # ✅ threshold before training AI model


def get_model_path(org_id: str) -> str:
    return os.path.join(MODELS_DIR, f"{org_id}_optimizer.pkl")


@router.post("/optimize-scheduling", response_model=schemas.OptimizerResponse)
def optimize_trip_scheduling(
    data: schemas.OptimizerRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin"))
):
    """
    AI-powered driver recommendation and auto-trip creation.
    Falls back to nearest-driver baseline if no trained model available.
    """
    org_id = current_user.organization_id
    model_path = get_model_path(str(org_id))

    # ✅ Step 1: Fetch all eligible drivers
    drivers = db.query(models.User).filter(
        models.User.role == "driver",
        models.User.organization_id == org_id,
        models.User.latitude.isnot(None),
        models.User.longitude.isnot(None)
    ).all()

    if not drivers:
        raise HTTPException(status_code=404, detail="No available drivers with location data.")

    # ✅ Step 2: Try loading org model
    model = None
    if os.path.exists(model_path):
        try:
            model = joblib.load(model_path)
        except Exception:
            model = None  # corrupted model file

    driver_predictions = []

    if model:
        # ✅ AI MODE: Use trained ML model
        for driver in drivers:
            distance_km = haversine_distance(driver.latitude, driver.longitude, data.pickup_lat, data.pickup_lon)

            df = pd.DataFrame([{
                "delivery_type": data.delivery_type,
                "priority_score": data.priority_score,
                "distance_to_pickup_km": distance_km,
                "driver_rating": driver.rating or 4.0,
            }])

            df = pd.get_dummies(df)

            for col in model.feature_names_in_:
                if col not in df.columns:
                    df[col] = 0

            df = df[model.feature_names_in_]

            predicted_score = model.predict(df)[0]
            driver_predictions.append((driver, distance_km, predicted_score))

        driver_predictions.sort(key=lambda x: x[2], reverse=True)
        prediction_method = "ml_model"

    else:
        # ✅ BASELINE MODE: Fallback to nearest driver
        for driver in drivers:
            distance_km = haversine_distance(driver.latitude, driver.longitude, data.pickup_lat, data.pickup_lon)
            driver_predictions.append((driver, distance_km, -distance_km))  # smaller distance = better score

        driver_predictions.sort(key=lambda x: x[1])  # sort by distance
        prediction_method = "baseline"

    if not driver_predictions:
        raise HTTPException(status_code=500, detail="Unable to make a driver prediction.")

    best_driver, best_distance, best_score = driver_predictions[0]

    # ✅ Step 3: Auto-create a trip
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

    # ✅ Step 4: Log activity
    log_activity(
        db=db,
        user_id=current_user.id,
        action="AI-Optimized Trip Assigned" if prediction_method == "ml_model" else "Baseline Trip Assigned",
        details=f"Driver {best_driver.name} assigned using {prediction_method}.",
        trip_id=trip.id
    )

    # ✅ Step 5: Return response
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
        ],
        prediction_method=prediction_method
    )