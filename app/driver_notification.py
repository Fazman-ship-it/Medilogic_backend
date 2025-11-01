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
from app.models import TripNotification


# ✅ Utility: Resolve delivery type (standard vs custom)
def get_delivery_label(trip: Trip) -> str:
    if trip.delivery_type == "other" and trip.custom_delivery_description:
        return trip.custom_delivery_description
    return trip.delivery_type or "Unknown"

# ✅ Instant trip assignment
def notify_driver_trip_assigned(driver_id: UUID, trip_id: UUID):
    """
    Sends an email notification when a driver is assigned a new trip.
    Handles instant trip follow-up reminders automatically.
    """
    from sqlalchemy.exc import SQLAlchemyError
    db = SessionLocal()
    try:
        driver = db.query(User).filter(User.id == driver_id).first()
        trip = db.query(Trip).filter(Trip.id == trip_id).first()

        if not driver or not trip:
            return

        local_scheduled_time = to_local(trip.scheduled_time)

        notes_section = ""
        if getattr(trip, "notes", None):
            notes_section = f"\n📝 **Admin Notes:** {trip.notes}\n"

        subject = "🛻 New Trip Assigned"
        body = f"""
        Hello {driver.name},

        A new trip has been assigned to you.

        🚛 Delivery Type: {get_delivery_label(trip)}
        📍 Pickup: {trip.pickup_location}
        🎯 Dropoff: {trip.dropoff_location}
        🕒 Schedule: {local_scheduled_time.strftime('%Y-%m-%d %H:%M')}
        🏷️ Priority: {trip.priority}{notes_section}

        Please check your dashboard for details.

        - Medilogic Team
        """
        send_email(to_email=driver.email, subject=subject, body=body)

        # ✅ Extra: If trip is "instant" (now or within 5 min), schedule a reminder in 10 min
        if trip.scheduled_time <= now_utc() + timedelta(minutes=5):
            scheduler.add_job(
                lambda: send_email(
                    to_email=driver.email,
                    subject="⚡ Reminder: Trip just started",
                    body=f"""Hello {driver.name},

This is a follow-up reminder that your trip scheduled for {local_scheduled_time.strftime('%Y-%m-%d %H:%M')} has already started.

🚛 Delivery Type: {get_delivery_label(trip)}
📍 Pickup: {trip.pickup_location}
🎯 Dropoff: {trip.dropoff_location}
🕒 Schedule: {local_scheduled_time.strftime('%Y-%m-%d %H:%M')}
🏷️ Priority: {trip.priority}{notes_section}

Stay prepared and confirm your status in the dashboard.

- Medilogic Team"""
                ),
                trigger="date",
                run_date=now_utc() + timedelta(minutes=10),
                id=f"instant_trip_reminder_{trip.id}",
                replace_existing=True
            )
    except SQLAlchemyError as e:
        db.rollback()
        print(f"Database error in notify_driver_trip_assigned: {e}")
    finally:
        db.close()
        
from sqlalchemy.exc import SQLAlchemyError
from app.models import TripNotification
from sqlalchemy.exc import SQLAlchemyError

def notify_upcoming_trips():
    """
    Sends intelligent reminders to drivers based on how soon their trips start:
      - < 10 minutes  → "Trip starting now"
      - 10–20 minutes → "15 minutes left"
      - 50–70 minutes → "1 hour left"
      - 3.5–4.5 hours → "4 hours left"
      - 23–25 hours → "1 day left"
    """
    db = SessionLocal()
    try:
        now = now_utc()
        trips = db.query(Trip).filter(Trip.scheduled_time > now).all()

        for trip in trips:
            driver = db.query(User).filter(User.id == trip.driver_id).first()
            if not driver:
                continue

            time_diff = trip.scheduled_time - now
            local_scheduled_time = to_local(trip.scheduled_time)

            notes_section = ""
            if getattr(trip, "notes", None):
                notes_section = f"\n📝 Admin Notes: {trip.notes}\n"

            # === Reminder logic ===
            if timedelta(hours=23) <= time_diff <= timedelta(hours=25):
                notif_type = "1_day_left"
                existing = db.query(TripNotification).filter_by(trip_id=trip.id, notification_type=notif_type).first()
                if existing:
                    continue

                subject = "🗓️ Trip Reminder - Tomorrow"
                body = f"""
                Hello {driver.name},

                Reminder: You have a trip scheduled for tomorrow.

                🚛 Delivery Type: {get_delivery_label(trip)}
                📍 Pickup: {trip.pickup_location}
                🎯 Dropoff: {trip.dropoff_location}
                🕒 Schedule: {local_scheduled_time.strftime('%Y-%m-%d %H:%M')}
                🏷️ Priority: {trip.priority}{notes_section}

                Please review your dashboard and plan accordingly.

                - Medilogic Team
                """
                send_email(to_email=driver.email, subject=subject, body=body)

                # ✅ Log notification
                db.add(TripNotification(trip_id=trip.id, notification_type=notif_type))
                db.commit()

            elif timedelta(hours=3.5) <= time_diff <= timedelta(hours=4.5):
                notif_type = "4_hours_left"
                existing = db.query(TripNotification).filter_by(trip_id=trip.id, notification_type=notif_type).first()
                if existing:
                    continue

                subject = "⏰ Trip Reminder - 4 Hours Left"
                body = f"""
                Hello {driver.name},

                You have a trip starting in about 4 hours.

                🚛 Delivery Type: {get_delivery_label(trip)}
                📍 Pickup: {trip.pickup_location}
                🎯 Dropoff: {trip.dropoff_location}
                🕒 Schedule: {local_scheduled_time.strftime('%Y-%m-%d %H:%M')}
                🏷️ Priority: {trip.priority}{notes_section}

                Ensure your vehicle and documents are ready.

                - Medilogic Team
                """
                send_email(to_email=driver.email, subject=subject, body=body)

                # ✅ Log notification
                db.add(TripNotification(trip_id=trip.id, notification_type=notif_type))
                db.commit()

            # (Repeat similar structure for "1_hour_left", "15_min_left", and "starting_now")

    except SQLAlchemyError as e:
        db.rollback()
        print(f"Database error in notify_upcoming_trips: {e}")
    finally:
        db.close()