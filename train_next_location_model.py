import random
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import joblib
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split

# 1. Generate fake location history for a single driver
def generate_fake_data(num_points=200):
    data = []
    base_lat, base_lon = 51.509865, -0.118092  # Central London
    current_time = datetime.now()

    for i in range(num_points):
        lat = base_lat + random.uniform(-0.01, 0.01)
        lon = base_lon + random.uniform(-0.01, 0.01)
        timestamp = current_time + timedelta(seconds=30 * i)
        data.append((lat, lon, timestamp))

    return pd.DataFrame(data, columns=["latitude", "longitude", "timestamp"])

# 2. Prepare data for ML (predict next lat/lon)
def prepare_features(df):
    df["lat_next"] = df["latitude"].shift(-1)
    df["lon_next"] = df["longitude"].shift(-1)
    df["time_delta"] = df["timestamp"].diff().dt.total_seconds().fillna(0)

    df = df[:-1]  # Remove last row (no next point)
    
    X = df[["latitude", "longitude", "time_delta"]]
    y = df[["lat_next", "lon_next"]]
    return X, y

# 3. Train and save model
def train_and_save_model():
    df = generate_fake_data()
    X, y = prepare_features(df)

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)

    score = model.score(X_test, y_test)
    print(f"Model trained. R² score: {score:.4f}")

    joblib.dump(model, "next_location_model.pkl")
    print("✅ Model saved as next_location_model.pkl")

if __name__ == "__main__":
    train_and_save_model()
