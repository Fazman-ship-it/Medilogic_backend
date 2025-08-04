from app.utilites.email_utilites import send_email  # Ensure this exists
from app.models import User, Notification
from app.database import SessionLocal

def send_compliance_alert(org_id, reason):
    db = SessionLocal()

    # Get all admins for the organization
    admins = db.query(User).filter(
        User.organization_id == org_id,
        User.role == "admin"
    ).all()

    for admin in admins:
        # 1. Send Email
        subject = "🚨 Compliance Alert"
        body = f"Dear {admin.full_name},\n\nYour organization has a compliance issue: {reason}.\n\nPlease review immediately in the Medilogic dashboard."
        send_email(to_email=admin.email, subject=subject, body=body)

        # 2. Create In-App Notification
        notif = Notification(
            user_id=admin.id,
            title="Compliance Alert",
            message=reason,
            type="compliance",
            is_read=False
        )
        db.add(notif)

    db.commit()
    db.close()