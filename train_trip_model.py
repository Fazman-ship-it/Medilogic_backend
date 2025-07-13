
# train_trip_model.py

import pandas as pd
import numpy as np
import joblib
import os
from sklearn.linear_model import LinearRegression
from sqlalchemy import create_engine
from dotenv import load_dotenv

# 1. Load environment variables
load_dotenv()

# 2. Construct DATABASE_URL from parts
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")

DATABASE_URL =f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# 3. Connect to the database
engine = create_engine(DATABASE_URL)

# Load trips from database
df = pd.read_sql("SELECT * FROM trips", engine)

# Check essential columns
required = ['distance_km', 'cost', 'delivery_type']
for col in required:
    if col not in df.columns:
        raise Exception(f"Missing required column: {col}")

# Simulate 'duration_minutes' if not present
if 'duration_minutes' not in df.columns:
    np.random.seed(42)
    df['duration_minutes'] = df['distance_km'] * 1.5 + df['cost'] * 0.2 + np.random.normal(5, 5, len(df))

# Encode delivery_type
df['delivery_type_encoded'] = df['delivery_type'].apply(lambda x: 1 if 'waste' in x.lower() else 0)

# Prepare features and target
X = df[['distance_km', 'cost', 'delivery_type_encoded']]
y = df['duration_minutes']

# Train model
model = LinearRegression()
model.fit(X, y)

# Save model to file
joblib.dump(model, "trip_duration_model.pkl")

print("✅ Model trained and saved as trip_duration_model.pkl")