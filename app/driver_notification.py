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

def notify_upcoming_trips():
    """
    Sends intelligent reminders to drivers based on how soon their trips start:
      - < 10 minutes  → "Trip starting now" reminder
      - 10–20 minutes → "15 minutes left" reminder
      - 50–70 minutes → "1 hour left" reminder
      Includes admin notes if available.
    """
    now = now_utc()
    trips = db.query(Trip).filter(Trip.scheduled_time > now).all()

    for trip in trips:
        driver = db.query(User).filter(User.id == trip.driver_id).first()
        if not driver:
            continue

        time_diff = trip.scheduled_time - now
        local_scheduled_time = to_local(trip.scheduled_time)

        # ✉️ Optional notes section
        notes_section = ""
        if getattr(trip, "notes", None):  # only include if notes exist
            notes_section = f"\n📝 **Admin Notes:** {trip.notes}\n"

        # 🚨 Trip starting now (less than 10 minutes)
        if time_diff < timedelta(minutes=10):
            subject = "⚡ Trip Starting Soon!"
            body = f"""
            Hello {driver.name},

            Your trip is starting now or within a few minutes!

            🚛 Delivery Type: {get_delivery_label(trip)}
            📍 Pickup: {trip.pickup_location}
            🎯 Dropoff: {trip.dropoff_location}
            🕒 Schedule: {local_scheduled_time.strftime('%Y-%m-%d %H:%M')}
            🏷️ Priority: {trip.priority}{notes_section}

            Please get ready immediately and confirm your status on the dashboard.

            - Medilogic Team
            """
            send_email(to_email=driver.email, subject=subject, body=body)

        # ⏱️ Trip starting in 10–20 minutes
        elif timedelta(minutes=10) <= time_diff <= timedelta(minutes=20):
            subject = "⏰ Trip Reminder - 15 Minutes Left"
            body = f"""
            Hello {driver.name},

            Reminder: You have a trip starting in about 15 minutes.

            🚛 Delivery Type: {get_delivery_label(trip)}
            📍 Pickup: {trip.pickup_location}
            🎯 Dropoff: {trip.dropoff_location}
            🕒 Schedule: {local_scheduled_time.strftime('%Y-%m-%d %H:%M')}
            🏷️ Priority: {trip.priority}{notes_section}

            Stay sharp — it's almost time!

            - Medilogic Team
            """
            send_email(to_email=driver.email, subject=subject, body=body)

        # 🕐 Trip starting in 50–70 minutes
        elif timedelta(minutes=50) <= time_diff <= timedelta(minutes=70):
            subject = "⏰ Trip Reminder - 1 Hour Left"
            body = f"""
            Hello {driver.name},

            Reminder: You have a trip starting in about 1 hour.

            🚛 Delivery Type: {get_delivery_label(trip)}
            📍 Pickup: {trip.pickup_location}
            🎯 Dropoff: {trip.dropoff_location}
            🕒 Schedule: {local_scheduled_time.strftime('%Y-%m-%d %H:%M')}
            🏷️ Priority: {trip.priority}{notes_section}

            Stay prepared and make sure everything is ready on your end.

            - Medilogic Team
            """
            send_email(to_email=driver.email, subject=subject, body=body)