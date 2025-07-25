# app/utilities/smart_scheduler.py

import pandas as pd
import joblib
import datetime
from typing import Optional
from app.models import Trip
from app import models
from sqlalchemy.orm import Session
from app.utilites.logging import log_activity

# Load model once
model = joblib.load("trip_duration_model.pkl")  # ✅ already trained and saved

def suggest_pickup_time_window(
    delivery_type: str,
    distance_km: float,
    cost: Optional[float] = None,
    user: Optional[models.User] = None,
    db: Optional[Session] = None
) -> dict:
    """
    Predicts optimal pickup time window based on delivery_type, distance, and cost.
    Returns a recommended time range in UTC.
    
    ✅ Multi-tenant-aware (user input optional)
    ✅ Optionally logs audit if user and db are provided
    """
    now = datetime.datetime.utcnow()

    data = {
        "distance_km": [distance_km],
        "cost": [cost or 0],
        "delivery_type": [delivery_type]
    }

    df = pd.DataFrame(data)
    df = pd.get_dummies(df)

    # Ensure all expected columns exist in the input
    expected_features = model.feature_names_in_
    for col in expected_features:
        if col not in df.columns:
            df[col] = 0  # Fill missing dummy columns with 0
    df = df[expected_features]

    predicted_minutes = model.predict(df)[0]
    estimated_duration = datetime.timedelta(minutes=predicted_minutes)

    pickup_start = now + datetime.timedelta(minutes=10)
    pickup_end = pickup_start + estimated_duration

    result = {
        "recommended_start_time": pickup_start.isoformat(),
        "recommended_end_time": pickup_end.isoformat(),
        "predicted_duration_minutes": round(predicted_minutes, 2)
    }

    # ✅ Optional: log activity for traceability
    if user and db:
        log_activity(
            db=db,
            user_id=user.id,
            action="ai_pickup_time_prediction",
            details=(
                f"Predicted pickup time window using AI. Delivery: {delivery_type}, "
                f"Distance: {distance_km}km, Cost: £{cost or 0}, "
                f"Start: {pickup_start.isoformat()}, End: {pickup_end.isoformat()}"
            )
        )

    return result