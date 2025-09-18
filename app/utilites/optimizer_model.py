# app/utilites/optimizer_model.py
import os
import joblib
import numpy as np
import pandas as pd
from typing import Optional
from sklearn.ensemble import RandomForestRegressor
from sqlalchemy.orm import Session
from app import models
from app.database import SessionLocal
from app.utilites.geolocation import haversine_distance

# Where models will be saved
MODEL_DIR = os.path.join(os.getcwd(), "models")
os.makedirs(MODEL_DIR, exist_ok=True)

# Minimum rows per organization to train a model
MIN_ROWS_TO_TRAIN = 10


def model_filepath(org_id: str) -> str:
    return os.path.join(MODEL_DIR, f"scheduler_optimizer_model_{org_id}.pkl")


def load_org_model(org_id: str):
    """Return loaded model or None if not found."""
    path = model_filepath(org_id)
    if not os.path.exists(path):
        return None
    return joblib.load(path)


def train_org_model(db: Session, org_id: str, min_rows: int = MIN_ROWS_TO_TRAIN):
    """
    Train optimizer model for the given org_id using historical trips (and driver info).
    Returns model or None if insufficient data.
    """
    trips = (
        db.query(models.Trip)
        .filter(models.Trip.organization_id == org_id, models.Trip.driver_id.isnot(None))
        .all()
    )

    rows = []
    for t in trips:
        # Driver rating
        drv = getattr(t, "driver", None)
        if drv is None and t.driver_id:
            drv = db.query(models.User).filter(models.User.id == t.driver_id).first()
        driver_rating = float(getattr(drv, "rating", None) or 4.0)

        # Distance (prefer stored)
        distance = getattr(t, "distance_km", None)
        if distance is None:
            lat1 = getattr(t, "pickup_lat", None) or getattr(t, "pickup_latitude", None)
            lon1 = getattr(t, "pickup_lon", None) or getattr(t, "pickup_longitude", None)
            lat2 = getattr(t, "dropoff_lat", None) or getattr(t, "dropoff_latitude", None)
            lon2 = getattr(t, "dropoff_lon", None) or getattr(t, "dropoff_longitude", None)
            if lat1 and lon1 and lat2 and lon2:
                distance = haversine_distance(lat1, lon1, lat2, lon2)
        if distance is None:
            distance = 0.0

        cost = float(getattr(t, "cost", 0) or 0)

        # Duration target
        duration = getattr(t, "duration_minutes", None)
        if duration is None:
            duration = distance * 1.5 + cost * 0.2

        target = -float(duration)  # shorter = better

        # Priority encoding
        pr = getattr(t, "priority", None) or ""
        priority_score = 1 if str(pr).lower() in {"urgent", "high"} else 0

        # Delivery type encoding
        if getattr(t, "delivery_type", None) == "other":
            delivery_label = getattr(t, "custom_delivery_description", "") or "other"
        else:
            delivery_label = getattr(t, "delivery_type", None) or "unknown"

        rows.append({
            "delivery_type": delivery_label,
            "priority_score": priority_score,
            "distance_to_pickup_km": float(distance),
            "driver_rating": driver_rating,
            "target": float(target)
        })

    if len(rows) < min_rows:
        print(f"⚠️ Not enough data to train model for org {org_id} ({len(rows)} rows)")
        return None

    df = pd.DataFrame(rows)

    # Features
    X = df[["delivery_type", "priority_score", "distance_to_pickup_km", "driver_rating"]].copy()
    X = pd.get_dummies(X, columns=["delivery_type"], drop_first=True)
    y = df["target"]

    # Train
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X, y)

    # Store feature names for later alignment
    model.feature_names_in_ = np.array(X.columns.tolist(), dtype=object)

    path = model_filepath(org_id)
    joblib.dump(model, path)

    print(f"✅ Trained and saved model for org {org_id} at {path}")
    return model


if __name__ == "__main__":
    # CLI entrypoint: train all orgs at once
    db = SessionLocal()

    orgs = db.query(models.Organization).all()
    for org in orgs:
        train_org_model(db, org.id)

    db.close()