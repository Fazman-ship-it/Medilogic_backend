
import os
import pickle
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.multioutput import MultiOutputRegressor
from sklearn.metrics import r2_score
from sqlalchemy.orm import Session
from app import models

def train_org_model(db: Session, org_id: str):
    """
    ✅ Train a next-location prediction model for a single organization.

    Args:
        db: SQLAlchemy DB session
        org_id: organization ID (string)

    Returns:
        model: trained model object, or None if insufficient data
    """

    # === 1️⃣ Query location + trip data for this org ===
    query = (
        db.query(
            models.DriverLocationHistory.latitude,
            models.DriverLocationHistory.longitude,
            models.DriverLocationHistory.timestamp,
            models.DriverLocationHistory.driver_id,
            models.Trip.delivery_type
        )
        .join(models.Trip, models.DriverLocationHistory.trip_id == models.Trip.id)
        .join(models.Organization, models.Trip.organization_id == models.Organization.id)
        .filter(models.Organization.id == org_id)
        .filter(models.DriverLocationHistory.latitude.isnot(None))
        .filter(models.DriverLocationHistory.longitude.isnot(None))
    )

    df = pd.read_sql(query.statement, db.bind)

    if df.empty or len(df) < 5:
        print(f"⚠️ Org {org_id} has insufficient data ({len(df)} samples). Skipping model training.")
        return None

    # === 2️⃣ Feature engineering ===
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df.dropna(subset=["timestamp"], inplace=True)
    df["latitude"] = df["latitude"].astype(float)
    df["longitude"] = df["longitude"].astype(float)
    df["hour"] = df["timestamp"].dt.hour
    df["day_of_week"] = df["timestamp"].dt.dayofweek
    df["delivery_type"] = df["delivery_type"].astype("category").cat.codes

    # Features and target
    X = df[["latitude", "longitude", "hour", "day_of_week", "driver_id", "delivery_type"]]
    y = df[["latitude", "longitude"]].shift(-1).dropna()
    X = X.iloc[:-1]  # align X and y

    # === 3️⃣ Train/test split ===
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    # === 4️⃣ Train model ===
    model = MultiOutputRegressor(RandomForestRegressor(n_estimators=100, random_state=42))
    model.fit(X_train, y_train)

    # Evaluate
    y_pred = model.predict(X_test)
    score = r2_score(y_test, y_pred)
    print(f"✅ Org {org_id}: Model trained. R² score: {score:.4f}")

    # === 5️⃣ Save model to org-specific path ===
    model_dir = "models"
    os.makedirs(model_dir, exist_ok=True)
    model_path = f"{model_dir}/next_location_model_org_{org_id}.pkl"
    with open(model_path, "wb") as f:
        pickle.dump(model, f)

    return model