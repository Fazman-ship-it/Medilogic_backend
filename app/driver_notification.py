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


def notify_driver_trip_assigned(driver_id: UUID, trip_id: UUID):
    """
    Sends an immediate email to a driver when a trip is assigned.
    """
    db: Session = SessionLocal()
    try:
        # ✅ Fetch driver and trip
        driver = db.query(User).filter(User.id == driver_id).first()
        trip = db.query(Trip).filter(Trip.id == trip_id).first()

        if not driver:
            print(f"[notify_driver_trip_assigned] Driver {driver_id} not found")
            return

        if not trip:
            print(f"[notify_driver_trip_assigned] Trip {trip_id} not found")
            return

        local_scheduled_time = (
            to_local(trip.scheduled_time) if trip.scheduled_time else "N/A"
        )

        notes_section = (
            f"\n📝 Admin Notes: {trip.notes}"
            if getattr(trip, "notes", None)
            else ""
        )

        subject = "🛻 New Trip Assigned"
        body = f"""
Hello {driver.name},

A new trip has been assigned to you.

🚛 Delivery Type: {get_delivery_label(trip)}
📍 Pickup: {trip.pickup_location}
🎯 Dropoff: {trip.dropoff_location}
🕒 Schedule: {local_scheduled_time}
🏷️ Priority: {trip.priority}{notes_section}

Please check your dashboard for details.

- Medilogic Team
"""

        send_email(to_email=driver.email, subject=subject, body=body)
        print(f"[notify_driver_trip_assigned] Email sent to {driver.email}")

    except Exception as e:
        db.rollback()
        print(f"[notify_driver_trip_assigned] Error: {e}")

    finally:
        db.close()


def notify_upcoming_trips():
    """
    Sends intelligent reminders to drivers based on how soon their trips start:
      - < 10 minutes  → "Trip starting now"
      - 10–20 minutes → "15 minutes left"
      - 50–70 minutes → "1 hour left"
      - 3.5–4.5 hours → "4 hours left"
      - 23–25 hours → "1 day left"
    """
    db: Session = SessionLocal()
    try:
        now = now_utc()
        trips = db.query(Trip).filter(Trip.scheduled_time > now).all()

        for trip in trips:
            if not trip.driver_id:
                continue

            driver = db.query(User).filter(User.id == trip.driver_id).first()
            if not driver:
                continue

            time_diff = trip.scheduled_time - now
            local_scheduled_time = to_local(trip.scheduled_time)

            notes_section = ""
            if getattr(trip, "notes", None):
                notes_section = f"\n📝 Admin Notes: {trip.notes}\n"

            # 🗓️ 1 DAY LEFT
            if timedelta(hours=23) <= time_diff <= timedelta(hours=25):
                notif_type = "1_day_left"
            # ⏰ 4 HOURS LEFT
            elif timedelta(hours=3.5) <= time_diff <= timedelta(hours=4.5):
                notif_type = "4_hours_left"
            else:
                continue

            existing = db.query(TripNotification).filter_by(
                trip_id=trip.id,
                notification_type=notif_type
            ).first()

            if existing:
                continue

            subject_map = {
                "1_day_left": "🗓️ Trip Reminder - Tomorrow",
                "4_hours_left": "⏰ Trip Reminder - 4 Hours Left",
            }

            subject = subject_map[notif_type]
            body = f"""
Hello {driver.name},

This is a reminder for your upcoming trip.

🚛 Delivery Type: {get_delivery_label(trip)}
📍 Pickup: {trip.pickup_location}
🎯 Dropoff: {trip.dropoff_location}
🕒 Schedule: {local_scheduled_time.strftime('%Y-%m-%d %H:%M')}
🏷️ Priority: {trip.priority}{notes_section}

Please ensure everything is prepared.

- Medilogic Team
"""

            send_email(to_email=driver.email, subject=subject, body=body)

            db.add(
                TripNotification(
                    trip_id=trip.id,
                    notification_type=notif_type
                )
            )
            db.commit()

    except SQLAlchemyError as e:
        db.rollback()
        print(f"[notify_upcoming_trips] Database error: {e}")

    finally:
        db.close()