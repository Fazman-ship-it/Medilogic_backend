from app.models import User
from app.utilites.email_utilites import send_email  # assuming you already have this

def send_daily_notification_to_all(db, subject: str, body: str):
    """Send daily notification to all verified users via SMTP."""
    users = db.query(User).filter(User.is_verified == True).all()

    for user in users:
        if user.email:
            send_email(
                to_email=user.email,
                subject=subject,
                body=body
            )