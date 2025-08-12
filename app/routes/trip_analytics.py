from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional
import pandas as pd
import joblib
import os
import plotly.graph_objs as go
import plotly.io as pio
from app import models
from app.database import get_db
from app.dependencies import require_role
from uuid import UUID

router = APIRouter(prefix="", tags=["Trip Analytics"])
# Load the trained ML model
MODEL_PATH = os.path.join(os.path.dirname(__file__), "../../trip_duration_model.pkl")
try:
    model = joblib.load(MODEL_PATH)
except Exception as e:
    model = None
    print(f"❌ Failed to load ML model: {e}")

@router.get("/trips/analytics")
def get_trip_analytics(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    status: Optional[str] = Query(None),
    driver_id: Optional[UUID] = Query(None),
    client_name: Optional[str] = Query(None),
    delivery_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_role("admin"))
):
    query = db.query(models.Trip)
    query = query.filter(models.Trip.organization_id == _.organization_id)  # ✅ Multi-tenant

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
    if not trips:
        return {"message": "No trips found for given filters."}

    # Convert trip data to DataFrame
    data = pd.DataFrame([{
        "distance_km": trip.distance_km,
        "cost": trip.cost,
        "delivery_type": trip.delivery_type
    } for trip in trips])

    # One-hot encode delivery_type
    if "delivery_type" in data.columns:
        data = pd.get_dummies(data, columns=["delivery_type"], drop_first=True)

    # Ensure all model features are present
    model_features = model.feature_names_in_
    for feature in model_features:
        if feature not in data.columns:
            data[feature] = 0
    data = data[model_features]

    # Make ML predictions
    predicted_durations = model.predict(data)

    # Aggregate stats
    total_trips = len(trips)
    total_distance = sum([trip.distance_km for trip in trips])
    total_cost = sum([trip.cost for trip in trips])
    average_cost = total_cost / total_trips if total_trips else 0

    delivery_types = [trip.delivery_type for trip in trips]
    most_common_type = max(set(delivery_types), key=delivery_types.count)

    # Create interactive chart
    type_counts = {}
    for trip in trips:
        type_counts[trip.delivery_type] = type_counts.get(trip.delivery_type, 0) + 1

    fig = go.Figure([go.Bar(x=list(type_counts.keys()), y=list(type_counts.values()))])
    fig.update_layout(title="Trips by Delivery Type", xaxis_title="Type", yaxis_title="Count")
    chart_html = pio.to_html(fig, full_html=False)

    # Simple AI Insight
    if total_trips > 30:
        ai_insight = "High delivery volume – consider route optimization."
    elif total_trips > 10:
        ai_insight = "Moderate activity detected – system operating normally."
    else:
        ai_insight = "Low trip volume – check for potential disruptions."

    return {
        "filters_applied": {
            "start_date": start_date,
            "end_date": end_date,
            "status": status,
            "driver_id": driver_id,
            "client_name": client_name,
            "delivery_type": delivery_type,
        },
        "analytics": {
            "total_trips": total_trips,
            "total_distance_km": round(total_distance, 2),
            "total_cost": round(total_cost, 2),
            "average_cost": round(average_cost, 2),
            "most_common_delivery_type": most_common_type,
        },
        "ai_prediction": {
            "predicted_durations_minutes": [round(d, 2) for d in predicted_durations],
            "average_predicted_duration": round(float(sum(predicted_durations) / total_trips), 2)
        },
        "ai_insight": ai_insight,
        "chart": chart_html
    } 


