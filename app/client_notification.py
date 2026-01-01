from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Trip, User
from app.utilites.email_utilites import send_email  # Adjust path if different
from app.utilites.time_utilities import  to_local, now_utc

from datetime import timedelta
from app.models import Trip, User
from app.database import SessionLocal
from app.utilites.email_utilites import send_email
from app.utilites.time_utilities import to_local, now_utc
from sqlalchemy.orm import Session

# ✅ Utility: Resolve delivery type (standard vs custom)
def get_delivery_label(trip: Trip) -> str:
    if trip.delivery_type == "other" and trip.custom_delivery_description:
        return trip.custom_delivery_description
    return trip.delivery_type or "Unknown"

def send_client_notifications():
    db: Session = SessionLocal()
    try:
        now = now_utc()  # ✅ use UTC-aware now

        # 1️⃣ Get all trips that are upcoming or just started
        trips = db.query(Trip).filter(
            Trip.scheduled_time >= now - timedelta(minutes=10),   # include instant trips
            Trip.scheduled_time <= now + timedelta(hours=24)      # within next 24h
        ).all()

        for trip in trips:
            client_user = db.query(User).filter(User.name == trip.client_name).first()

            if not (client_user and client_user.email):
                continue

            # Time difference between trip and now
            time_to_trip = (trip.scheduled_time - now).total_seconds() / 60  # in minutes

            subject = None
            body = None

            local_scheduled_time = to_local(trip.scheduled_time)  # 🔹 convert to local for emails

            # 2️⃣ Instant trip → send immediately and again 10 mins later
            if time_to_trip <= 0:
                subject = "Instant Trip Started"
                body = f"""
                Dear {client_user.name},

                Your instant trip has been created and is now active.

                Pickup Location: {trip.pickup_location}
                Dropoff Location: {trip.dropoff_location}
                Delivery Type: {get_delivery_label(trip)}
                Priority Level: {trip.priority.value if trip.priority else 'Normal'}

                Thank you for using MediLogic.
                """
            elif 0 < time_to_trip <= 10:
                subject = "Instant Trip Confirmation (Follow-up)"
                body = f"""
                Dear {client_user.name},

                Just to confirm, your instant trip is in progress.

                Pickup Location: {trip.pickup_location}
                Dropoff Location: {trip.dropoff_location}
                Delivery Type: {get_delivery_label(trip)}
                Priority Level: {trip.priority.value if trip.priority else 'Normal'}

                Best regards,
                MediLogic Team
                """
            # 3️⃣ 1 hour before reminder
            elif 55 <= time_to_trip <= 65:
                subject = "Reminder: Trip in 1 Hour"
                body = f"""
                Dear {client_user.name},

                This is a reminder that your trip is scheduled to start in 1 hour.

                Pickup Location: {trip.pickup_location}
                Dropoff Location: {trip.dropoff_location}
                Delivery Type: {get_delivery_label(trip)}
                Scheduled Time: {local_scheduled_time.strftime('%Y-%m-%d %H:%M')} (UK time)

                Thank you for using MediLogic.
                """
            # 4️⃣ 15 minutes before reminder
            elif 10 <= time_to_trip <= 20:
                subject = "Reminder: Trip in 15 Minutes"
                body = f"""
                Dear {client_user.name},

                This is a reminder that your trip will start in 15 minutes.

                Pickup Location: {trip.pickup_location}
                Dropoff Location: {trip.dropoff_location}
                Delivery Type: {get_delivery_label(trip)}
                Scheduled Time: {local_scheduled_time.strftime('%Y-%m-%d %H:%M')} (UK time)

                Please be ready.

                Best regards,
                MediLogic Team
                """

            # Only send if subject/body was set
            if subject and body:
                # ✅ Using positional arguments
                 send_email(client_user.email, subject, body)

    finally:
        db.close()