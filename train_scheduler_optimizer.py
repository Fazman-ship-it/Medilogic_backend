# train_scheduler_optimizer.py

import pandas as pd
import joblib
from sklearn.linear_model import LinearRegression
from sqlalchemy import create_engine
from dotenv import load_dotenv
import os

# ✅ Load environment variables from .env
load_dotenv()

# ✅ Read from .env with correct key names
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# ✅ Connect to PostgreSQL using SQLAlchemy
engine = create_engine(DATABASE_URL)

# ✅ Query historical trip data
query = """
SELECT distance_km, cost, EXTRACT(hour FROM scheduled_time) AS hour, EXTRACT(dow FROM scheduled_time) AS day_of_week
FROM trips
WHERE status IN ('completed', 'assigned') AND distance_km IS NOT NULL AND cost IS NOT NULL
"""

df = pd.read_sql(query, engine)

# ✅ Clean data
df.dropna(inplace=True)

# ✅ Define input and output features
X = df[["distance_km", "cost", "day_of_week"]]
y = df["hour"]  # target = best pickup hour

# ✅ Train model
model = LinearRegression()
model.fit(X, y)

# ✅ Save model to disk
model_path = os.path.join("models", "scheduler_optimizer_model.pkl")
os.makedirs("models", exist_ok=True)
joblib.dump(model, model_path)

print("✅ Scheduler optimizer model trained and saved at:", model_path)