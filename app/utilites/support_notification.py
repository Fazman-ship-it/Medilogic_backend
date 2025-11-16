from app.utilites.email_utilites import send_email  # ✅ assuming you already have a generic send_email utility
from sqlalchemy.orm import Session
from app import models


def notify_ticket_users(db: Session, ticket: models.SupportTicket, sender: models.User, message: str):
    """
    Notify the correct users when a new message or reply is created.
    """

    recipient_emails = set()  # avoid duplicates

    # --- 1. Notify main ticket owner (client/driver) ---
    if ticket.user and ticket.user.email and ticket.user.id != sender.id:
        recipient_emails.add(ticket.user.email)

    # --- 2. Notify admins of the ticket organization ---
    if ticket.organization_id:
        admins = db.query(models.User).filter(
            models.User.organization_id == ticket.organization_id,
            models.User.role == "admin",
            models.User.id != sender.id
        ).all()
        for admin in admins:
            if admin.email:
                recipient_emails.add(admin.email)

    # --- 3. Notify super admin ---
    super_admins = db.query(models.User).filter(models.User.role == "super_admin").all()
    for sa in super_admins:
        if sa.email and sa.id != sender.id:
            recipient_emails.add(sa.email)

    # --- Send email ---
    subject = f"New Support Message on Ticket: {ticket.subject}"
    body = f"""
You have a new message on a support ticket.

Ticket Subject: {ticket.subject}
From: {sender.name} ({sender.role})
Message:
{message}

Please log in to your dashboard to view and reply.
"""

    for email in recipient_emails:
        send_email(email, subject, body)