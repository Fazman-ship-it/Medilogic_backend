import pandas as pd
import numpy as np
import joblib
import os
from sklearn.linear_model import LinearRegression
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# 1. Load environment variables
load_dotenv()

# 2. Construct DATABASE_URL from parts
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# 3. Connect to the database
engine = create_engine(DATABASE_URL)

# Create output folder for models
os.makedirs("trip_models", exist_ok=True)

# Get all organization IDs that have trips
with engine.connect() as conn:
    org_ids = conn.execute(text("SELECT DISTINCT organization_id FROM trips WHERE organization_id IS NOT NULL")).fetchall()
    org_ids = [row[0] for row in org_ids]

print(f"🏢 Found {len(org_ids)} organizations with trips.")

# ✅ Train a separate model per organization
for org_id in org_ids:
    print(f"\n🔹 Training model for org: {org_id}")

    # Load trips only for this organization
    query = f"SELECT * FROM trips WHERE organization_id = '{org_id}'"
    df = pd.read_sql(query, engine)

    print(f"📊 Loaded {len(df)} rows for org {org_id}")

    # ✅ Ensure required columns exist
    required = ['distance_km', 'cost', 'delivery_type']
    if not all(col in df.columns for col in required):
        print(f"⚠️ Skipping org {org_id} (missing required columns).")
        continue

    # ✅ Handle missing values
    df['distance_km'] = df['distance_km'].fillna(0)
    df['cost'] = df['cost'].fillna(0)
    df['delivery_type'] = df['delivery_type'].fillna("unknown")

    # ✅ Simulate duration_minutes if not present
    if 'duration_minutes' not in df.columns:
        np.random.seed(42)
        df['duration_minutes'] = (
            df['distance_km'] * 1.5
            + df['cost'] * 0.2
            + np.random.normal(5, 5, len(df))
        )

    # ✅ Encode delivery_type
    df['delivery_type_encoded'] = df['delivery_type'].apply(
        lambda x: 1 if isinstance(x, str) and 'waste' in x.lower() else 0
    )

    # Prepare features and target
    X = df[['distance_km', 'cost', 'delivery_type_encoded']]
    y = df['duration_minutes']

    # ✅ Guard against empty dataset
    if X.empty or y.empty:
        print(f"⚠️ Skipping org {org_id} (no valid data).")
        continue

    # Train model
    model = LinearRegression()
    model.fit(X, y)

    # Save model with org ID
    model_path = f"trip_models/trip_duration_model_org_{org_id}.pkl"
    joblib.dump(model, model_path)

    print(f"✅ Model for org {org_id} saved at {model_path}")