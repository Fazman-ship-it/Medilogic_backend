# app/utilities/smart_scheduler.py

import pandas as pd
import joblib
import datetime
import os
from typing import Optional
from app.models import Trip
from app import models
from sqlalchemy.orm import Session
from app.utilites.logging import log_activity



def load_org_model(org_id: str):
    """Load the ML model for a specific organization."""
    model_path = f"trip_models/trip_duration_model_org_{org_id}.pkl"
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"⚠️ No trained model found for organization {org_id}. Please train first.")
    return joblib.load(model_path)

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
    
    ✅ Multi-tenant-aware (loads model per organization_id)
    ✅ Optionally logs audit if user and db are provided
    """
    if not user or not user.organization_id:
        raise ValueError("❌ User with valid organization_id is required to predict pickup time.")

    # 🔹 Load the correct organization model
    model = load_org_model(user.organization_id)

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