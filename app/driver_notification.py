# app/notifications/driver_notifications.py

from datetime import datetime, timedelta
from app.utilites. email_utilites import send_email  # Adjust if your path differs
from app.models import Trip, User
from app.database import SessionLocal
from zoneinfo import ZoneInfo
from uuid import UUID
from app import scheduler  # Assuming you have a scheduler setup
from app.utilites.time_utilities import to_utc, to_local, now_utc
from datetime import datetime, timedelta
from app.utilites.email_utilites import send_email  # Adjust if your path differs
from app.models import Trip, User
from app.database import SessionLocal
from zoneinfo import ZoneInfo
from uuid import UUID
from app import scheduler  # Assuming you have a scheduler setup
from app.utilites.time_utilities import to_utc, to_local, now_utc

db = SessionLocal()

# ✅ Utility: Resolve delivery type (standard vs custom)
def get_delivery_label(trip: Trip) -> str:
    if trip.delivery_type == "other" and trip.custom_delivery_description:
        return trip.custom_delivery_description
    return trip.delivery_type or "Unknown"

# ✅ Instant trip assignment
def notify_driver_trip_assigned(driver_id: UUID, trip_id: UUID):
    driver = db.query(User).filter(User.id == driver_id).first()
    trip = db.query(Trip).filter(Trip.id == trip_id).first()

    if not driver or not trip:
        return

    local_scheduled_time = to_local(trip.scheduled_time)

    subject = "🛻 New Trip Assigned"
    body = f"""
    Hello {driver.name},

    A new trip has been assigned to you.

    🚛 Delivery Type: {get_delivery_label(trip)}
    📍 Pickup: {trip.pickup_location}
    🎯 Dropoff: {trip.dropoff_location}
    🕒 Schedule: {local_scheduled_time.strftime('%Y-%m-%d %H:%M')}
    🏷️ Priority: {trip.priority}

    Please check your dashboard for details.

    - Medilogic Team
    """
    send_email(to_email=driver.email, subject=subject, body=body)

    # ✅ Extra: If trip is "instant" (now or past time), send another in 10 min
    if trip.scheduled_time <= now_utc() + timedelta(minutes=5):
        scheduler.add_job(
            lambda: send_email(
                to_email=driver.email,
                subject="⚡ Reminder: Trip just started",
                body=f"Hello {driver.name},\n\nThis is a follow-up reminder that your trip scheduled for {local_scheduled_time.strftime('%Y-%m-%d %H:%M')} has already started.\n\nStay prepared!\n\n- Medilogic Team"
            ),
            trigger="date",
            run_date=now_utc() + timedelta(minutes=10),
            id=f"instant_trip_reminder_{trip.id}",
            replace_existing=True
        )

# ✅ Scheduled reminders (1h before + 15m before)
def notify_upcoming_trips():
    """
    Sends reminders to drivers:
      - 1 hour before their scheduled trips
      - 15 minutes before their scheduled trips
    """
    now = now_utc()  # 🔹 use UTC-aware now
    one_hour_from_now = now + timedelta(hours=1)
    fifteen_minutes_from_now = now + timedelta(minutes=15)

    # --- Trips starting in the next hour ---
    trips_one_hour = db.query(Trip).filter(
        Trip.scheduled_time.between(now, one_hour_from_now)
    ).all()

    for trip in trips_one_hour:
        driver = db.query(User).filter(User.id == trip.driver_id).first()
        if driver:
            local_scheduled_time = to_local(trip.scheduled_time)
            subject = "⏰ Trip Reminder - 1 Hour Left"
            body = f"""
            Hello {driver.name},

            Reminder: You have a trip starting in 1 hour.

            🚛 Delivery Type: {get_delivery_label(trip)}
            📍 Pickup: {trip.pickup_location}
            🎯 Dropoff: {trip.dropoff_location}
            🕒 Schedule: {local_scheduled_time.strftime('%Y-%m-%d %H:%M')}
            🏷️ Priority: {trip.priority}

            Stay prepared!

            - Medilogic Team
            """
            send_email(to_email=driver.email, subject=subject, body=body)

    # --- Trips starting in the next 15 minutes ---
    trips_fifteen_minutes = db.query(Trip).filter(
        Trip.scheduled_time.between(now, fifteen_minutes_from_now)
    ).all()

    for trip in trips_fifteen_minutes:
        driver = db.query(User).filter(User.id == trip.driver_id).first()
        if driver:
            local_scheduled_time = to_local(trip.scheduled_time)
            subject = "⚡ Trip Reminder - 15 Minutes Left"
            body = f"""
            Hello {driver.name},

            Reminder: You have a trip starting in 15 minutes.
            🚛 Delivery Type: {get_delivery_label(trip)}
            📍 Pickup: {trip.pickup_location}
            🎯 Dropoff: {trip.dropoff_location}
            🕒 Schedule: {local_scheduled_time.strftime('%Y-%m-%d %H:%M')}
            🏷️ Priority: {trip.priority}

            Stay sharp — it's almost time!

            - Medilogic Team
            """
            send_email(to_email=driver.email, subject=subject, body=body)