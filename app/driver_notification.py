# app/notifications/driver_notifications.py

from datetime import datetime, timedelta
from app.utilites. email_utilites import send_email  # Adjust if your path differs
from app.models import Trip, User
from app.database import SessionLocal
from zoneinfo import ZoneInfo
from uuid import UUID
from app import scheduler  # Assuming you have a scheduler setup

db = SessionLocal()

# --- Keep your pick_and_send_daily_notification as is ---
# --- Keep your scheduler daily notification as is ---

# ✅ Instant trip assignment
def notify_driver_trip_assigned(driver_id: UUID, trip_id: UUID):
    driver = db.query(User).filter(User.id == driver_id).first()
    trip = db.query(Trip).filter(Trip.id == trip_id).first()

    if not driver or not trip:
        return

    subject = "🛻 New Trip Assigned"
    body = f"""
    Hello {driver.name},

    A new trip has been assigned to you.

    🚛 Delivery Type: {trip.delivery_type}
    📍 Pickup: {trip.pickup_location}
    🎯 Dropoff: {trip.dropoff_location}
    🕒 Schedule: {trip.scheduled_time.astimezone(ZoneInfo("Europe/London")).strftime('%Y-%m-%d %H:%M')}
    🏷️ Priority: {trip.priority}

    Please check your dashboard for details.

    - Medilogic Team
    """
    send_email(to_email=driver.email, subject=subject, body=body)

    # ✅ Extra: If trip is "instant" (now or past time), send another in 10 min
    if trip.scheduled_time <= datetime.utcnow() + timedelta(minutes=5):
        scheduler.add_job(
            lambda: send_email(
                to_email=driver.email,
                subject="⚡ Reminder: Trip just started",
                body=f"Hello {driver.name},\n\nThis is a follow-up reminder that your trip scheduled for {trip.scheduled_time.astimezone(ZoneInfo('Europe/London')).strftime('%Y-%m-%d %H:%M')} has already started. Stay prepared!\n\n- Medilogic Team"
            ),
            trigger="date",
            run_date=datetime.utcnow() + timedelta(minutes=10),
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
    now = datetime.utcnow()
    one_hour_from_now = now + timedelta(hours=1)
    fifteen_minutes_from_now = now + timedelta(minutes=15)

    # --- Trips starting in the next hour ---
    trips_one_hour = db.query(Trip).filter(
        Trip.scheduled_time.between(now, one_hour_from_now)
    ).all()

    for trip in trips_one_hour:
        driver = db.query(User).filter(User.id == trip.driver_id).first()
        if driver:
            subject = "⏰ Trip Reminder - 1 Hour Left"
            body = f"""
            Hello {driver.name},

            Reminder: You have a trip starting in 1 hour.

            🚛 Delivery Type: {trip.delivery_type}
            📍 Pickup: {trip.pickup_location}
            🎯 Dropoff: {trip.dropoff_location}
            🕒 Schedule: {trip.scheduled_time.astimezone(ZoneInfo("Europe/London")).strftime('%Y-%m-%d %H:%M')}
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
            subject = "⚡ Trip Reminder - 15 Minutes Left"
            body = f"""
            Hello {driver.name},

            Reminder: You have a trip starting in 15 minutes.

            🚛 Delivery Type: {trip.delivery_type}
            📍 Pickup: {trip.pickup_location}
            🎯 Dropoff: {trip.dropoff_location}
            🕒 Schedule: {trip.scheduled_time.astimezone(ZoneInfo("Europe/London")).strftime('%Y-%m-%d %H:%M')}
            🏷️ Priority: {trip.priority}

            Stay sharp — it's almost time!

            - Medilogic Team
            """
            send_email(to_email=driver.email, subject=subject, body=body)