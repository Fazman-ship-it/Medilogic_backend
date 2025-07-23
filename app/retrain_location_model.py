def retrain_location_model():
    import os
    import pickle
    import pandas as pd
    import numpy as np
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.model_selection import train_test_split
    from sklearn.multioutput import MultiOutputRegressor
    from sklearn.metrics import r2_score
    from dotenv import load_dotenv
    from sqlalchemy import create_engine
    from datetime import datetime

    load_dotenv()

    DB_USER = os.getenv("DB_USER")
    DB_PASSWORD = os.getenv("DB_PASSWORD")
    DB_HOST = os.getenv("DB_HOST")
    DB_PORT = os.getenv("DB_PORT")
    DB_NAME = os.getenv("DB_NAME")
    DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

    engine = create_engine(DATABASE_URL)

    query = """
    SELECT l.latitude, l.longitude, l.timestamp, l.driver_id, t.delivery_type
    FROM driver_location_history l
    JOIN trips t ON l.trip_id = t.id
    WHERE l.latitude IS NOT NULL AND l.longitude IS NOT NULL
    """

    df = pd.read_sql(query, engine)

    if df.empty:
        print("⚠️ No data available in driver_location_history. Skipping training.")
        return

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors='coerce')
    df.dropna(subset=["timestamp"], inplace=True)
    df["latitude"] = df["latitude"].astype(float)
    df["longitude"] = df["longitude"].astype(float)
    df["hour"] = df["timestamp"].dt.hour
    df["day_of_week"] = df["timestamp"].dt.dayofweek
    df["delivery_type"] = df["delivery_type"].astype("category").cat.codes

    X = df[["latitude", "longitude", "hour", "day_of_week", "driver_id", "delivery_type"]]
    y = df[["latitude", "longitude"]].shift(-1).dropna()
    X = X.iloc[:-1]

    if len(X) < 5:
        print(f"⚠️ Not enough data to train model (only {len(X)} samples).")
        return

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    model = MultiOutputRegressor(RandomForestRegressor(n_estimators=100, random_state=42))
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    score = r2_score(y_test, y_pred)
    print(f"✅ Model trained. R² score: {score:.4f}")


    model = None

    model_path = "next_location_model_v2.pkl"
    if os.path.exists(model_path):
        with open(model_path, "rb") as f:
            model = pickle.load(f)
        print("✅ Prediction model loaded.")
    else:
        print("⚠️ Prediction model not found. Skipping predictions until model is trained.")    