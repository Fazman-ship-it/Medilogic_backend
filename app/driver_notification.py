# app/notifications/driver_notifications.py

from datetime import datetime, timedelta
from app.utilites. email_utilites import send_email  # Adjust if your path differs
from app.models import Trip, User
from app.database import SessionLocal
from zoneinfo import ZoneInfo
from uuid import UUID

db = SessionLocal()

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

def notify_upcoming_trips():
    """
    Sends reminders to drivers 1 hour before their scheduled trips.
    Can be called via a scheduler (e.g., APScheduler).
    """
    one_hour_from_now = datetime.utcnow() + timedelta(hours=1)
    trips = db.query(Trip).filter(
        Trip.scheduled_time.between(datetime.utcnow(), one_hour_from_now)
    ).all()

    for trip in trips:
        driver = db.query(User).filter(User.id == trip.driver_id).first()
        if driver:
            subject = "⏰ Upcoming Trip Reminder"
            body = f"""
            Hello {driver.name},

            This is a reminder for your upcoming trip:

            🚛 Delivery Type: {trip.delivery_type}
            📍 Pickup: {trip.pickup_location}
            🎯 Dropoff: {trip.dropoff_location}
            🕒 Schedule: {trip.scheduled_time.astimezone(ZoneInfo("Europe/London")).strftime('%Y-%m-%d %H:%M')}
            🏷️ Priority: {trip.priority}

            Stay prepared!

            - Medilogic Team
            """
            send_email(to_email=driver.email, subject=subject, body=body)