from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Trip, User
from app.utilites.email_utilites import send_email  # Adjust path if different

def send_client_notifications():
    db: Session = SessionLocal()
    try:
        # Find trips scheduled within the next 24 hours
        upcoming = datetime.utcnow() + timedelta(hours=24)
        now = datetime.utcnow()

        trips = db.query(Trip).filter(
            Trip.scheduled_time >= now,
            Trip.scheduled_time <= upcoming
        ).all()

        for trip in trips:
            client_user = db.query(User).filter(User.name == trip.client_name).first()
            if client_user and client_user.email:
                subject = f"Upcoming Trip Scheduled"
                body = f"""
                Dear {client_user.name},

                This is a reminder that a trip has been scheduled for:

                Pickup Location: {trip.pickup_location}
                Dropoff Location: {trip.dropoff_location}
                Delivery Type: {trip.delivery_type}
                Scheduled Time: {trip.scheduled_time.strftime('%Y-%m-%d %H:%M')} (UK time)
                Priority Level: {trip.priority.value if trip.priority else 'Normal'}

                Thank you for using MediLogic.

                Best regards,
                MediLogic Team
                """
                send_email(to=client_user.email, subject=subject, body=body)

    finally:
        db.close()