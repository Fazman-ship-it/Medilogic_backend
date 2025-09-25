from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional
import pandas as pd
import joblib
import os
from app import models
from app.database import get_db
from app.dependencies import require_role
from uuid import UUID
from sklearn.linear_model import LinearRegression
import numpy as np
from app.schemas import TripAnalyticsResponse

router = APIRouter(prefix="", tags=["Trip Analytics"])

@router.get("/trips/analytics", response_model=TripAnalyticsResponse)
def get_trip_analytics(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    status: Optional[str] = Query(None),
    driver_id: Optional[UUID] = Query(None),
    client_name: Optional[str] = Query(None),
    delivery_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin"))
):
    query = db.query(models.Trip)
    query = query.filter(models.Trip.organization_id == current_user.organization_id)  # ✅ Multi-tenant

    # Apply filters safely
    try:
        if start_date:
            start_date = datetime.strptime(start_date, "%Y-%m-%d")
            query = query.filter(models.Trip.scheduled_time >= start_date)
        if end_date:
            end_date = datetime.strptime(end_date, "%Y-%m-%d")
            query = query.filter(models.Trip.scheduled_time <= end_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    if status:
        query = query.filter(models.Trip.status == status)
    if driver_id:
        query = query.filter(models.Trip.driver_id == driver_id)
    if client_name:
        query = query.filter(models.Trip.client_name.ilike(f"%{client_name}%"))
    if delivery_type:
        query = query.filter(models.Trip.delivery_type == delivery_type)

    trips = query.all()

    # ✅ Return gracefully if no trips match filters
    if not trips:
        return {
            "message": "No trips found for given filters.",
            "filters_applied": {
                "start_date": start_date.strftime("%Y-%m-%d") if isinstance(start_date, datetime) else start_date,
                "end_date": end_date.strftime("%Y-%m-%d") if isinstance(end_date, datetime) else end_date,
                "status": status,
                "driver_id": str(driver_id) if driver_id else None,
                "client_name": client_name,
                "delivery_type": delivery_type,
            },
            "analytics": {},
            "ai_prediction": {},
            "ai_insight": "No data available for selected filters."
        }

    # ✅ Org-specific model path
    org_id = str(current_user.organization_id)
    model_path = f"trip_models/trip_duration_model_org_{org_id}.pkl"

    # Load or auto-train model
    try:
        model = joblib.load(model_path)
    except Exception:
        df = pd.DataFrame([{
            "distance_km": trip.distance_km or 0,
            "cost": trip.cost or 0,
            "delivery_type": trip.delivery_type or "unknown"
        } for trip in trips])

        np.random.seed(42)
        df["duration_minutes"] = (
            df["distance_km"] * 1.5
            + df["cost"] * 0.2
            + np.random.normal(5, 5, len(df))
        )

        df["delivery_type_encoded"] = df["delivery_type"].apply(
            lambda x: 1 if isinstance(x, str) and "waste" in x.lower() else 0
        )

        X = df[["distance_km", "cost", "delivery_type_encoded"]]
        y = df["duration_minutes"]

        if X.empty or y.empty:
            # ✅ Instead of 500, return no-data gracefully
            return {
                "message": "Not enough data to train a model for this organization.",
                "filters_applied": {
                    "start_date": start_date.strftime("%Y-%m-%d") if isinstance(start_date, datetime) else start_date,
                    "end_date": end_date.strftime("%Y-%m-%d") if isinstance(end_date, datetime) else end_date,
                    "status": status,
                    "driver_id": str(driver_id) if driver_id else None,
                    "client_name": client_name,
                    "delivery_type": delivery_type,
                },
                "analytics": {},
                "ai_prediction": {},
                "ai_insight": "No data available for selected filters."
            }

        model = LinearRegression()
        model.fit(X, y)
        os.makedirs("trip_models", exist_ok=True)
        joblib.dump(model, model_path)
        print(f"⚡ Auto-trained model for org {org_id} and saved to {model_path}")

    # Prepare trip data for prediction
    data = pd.DataFrame([{
        "distance_km": trip.distance_km or 0,
        "cost": trip.cost or 0,
        "delivery_type_encoded": 1 if trip.delivery_type and "waste" in trip.delivery_type.lower() else 0
    } for trip in trips])

    model_features = model.feature_names_in_
    for feature in model_features:
        if feature not in data.columns:
            data[feature] = 0
    data = data[model_features]

    # Predictions
    predicted_durations = model.predict(data)

    # Aggregates
    total_trips = len(trips)
    total_distance = sum([trip.distance_km or 0 for trip in trips])
    total_cost = sum([trip.cost or 0 for trip in trips])
    average_cost = total_cost / total_trips if total_trips else 0

    # Handle delivery types safely
    delivery_types = []
    for trip in trips:
        if trip.delivery_type == "other" and trip.custom_delivery_description:
            delivery_types.append(trip.custom_delivery_description)
        else:
            delivery_types.append(trip.delivery_type or "unknown")

    most_common_type = (
        max(set(delivery_types), key=delivery_types.count) if delivery_types else "unknown"
    )

    # Count trips per delivery type (for frontend charting)
    type_counts = {}
    for trip in trips:
        if trip.delivery_type == "other" and trip.custom_delivery_description:
            dtype = trip.custom_delivery_description
        else:
            dtype = trip.delivery_type or "unknown"
        type_counts[dtype] = type_counts.get(dtype, 0) + 1

    # AI insight
    if total_trips > 30:
        ai_insight = "High delivery volume – consider route optimization."
    elif total_trips > 10:
        ai_insight = "Moderate activity detected – system operating normally."
    else:
        ai_insight = "Low trip volume – check for potential disruptions."

    # ✅ Return JSON-only data
    return {
        "filters_applied": {
            "start_date": start_date.strftime("%Y-%m-%d") if isinstance(start_date, datetime) else start_date,
            "end_date": end_date.strftime("%Y-%m-%d") if isinstance(end_date, datetime) else end_date,
            "status": status,
            "driver_id": str(driver_id) if driver_id else None,
            "client_name": client_name,
            "delivery_type": delivery_type,
        },
        "analytics": {
            "total_trips": total_trips,
            "total_distance_km": round(total_distance, 2),
            "total_cost": round(total_cost, 2),
            "average_cost": round(average_cost, 2),
            "most_common_delivery_type": most_common_type,
            "trips_per_delivery_type": type_counts,
        },
        "ai_prediction": {
            "predicted_durations_minutes": [round(d, 2) for d in predicted_durations],
            "average_predicted_duration": round(float(sum(predicted_durations) / total_trips), 2)
        },
        "ai_insight": ai_insight
    }