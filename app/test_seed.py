
from sqlalchemy.orm import Session
from app.database import SessionLocal
from datetime import datetime
from app.config import settings
from app import models

# Seed the database
db: Session = SessionLocal()

# Sample trips
sample_trips = [
    models.Trip(
        driver_id=1,
        driver_name="John Doe",
        delivery_type="clinical_waste",
        scheduled_time="2025-07-01 09:00:00",
        cost=120.5,
        client_name="Central Clinic",
        pickup_location="10 Downing St, London",
        dropoff_location="23 Hospital Rd, London",
        distance_km=18.3,
        status="scheduled",
        location_zone="Zone A",
        vehicle_type="van",
        shift_window="morning",
        compliance_flag=True,
        priority="urgent",
        created_by="admin",
        recurrence_rule="weekly"
    ),
    models.Trip(
        driver_id=2,
        driver_name="Sarah Smith",
        delivery_type="pharma_delivery",
        scheduled_time="2025-07-03 14:00:00",
        cost=95.0,
        client_name="West Health Centre",
        pickup_location="15 Station Rd, Birmingham",
        dropoff_location="32 Clinic Ln, Birmingham",
        distance_km=12.7,
        priority="normal",
        status="completed",
        location_zone="Zone B",
        vehicle_type="bike",
        shift_window="afternoon",
        compliance_flag=False,
        created_by="admin",
        recurrence_rule="none"
    )
]

for trip in sample_trips:
    db.add(trip)

db.commit()
db.close()

print("✅ Trip table reset and seeded with 2 example trips.")