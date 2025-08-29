# app/utils/subscription_utils.py

from app.utilites.email_utilites import send_email   # your existing email sending utility
from app.schemas import BadgeType, SubscriptionPlan

def send_subscription_email(to_email: str, full_name: str, badge: BadgeType, plan: SubscriptionPlan):
    """
    Send a subscription confirmation email to a Medilogic driver.
    
    - Green (£7.99): can upload docs + profile boost + view counts
    - Blue (£12.99): all Green benefits + analytics graphs + org names
    """
    # Build email subject and body
    subject = f"Medilogic Subscription Upgrade: {badge.value.title()} Badge Activated"
    
    if badge == BadgeType.green:
        benefits = [
            "Upload essential documents",
            "Profile boost for faster visibility",
            "View counts of organizations checking your profile"
        ]
    elif badge == BadgeType.blue:
        benefits = [
            "All Green badge benefits",
            "Analytics and engagement graphs",
            "See organization names that viewed your profile"
        ]
    else:
        benefits = ["Limited free access – upgrade to Green or Blue for full benefits"]

    body = f"""
    Hello {full_name},

    Your Medilogic subscription has been updated to: {plan.value.title()} ({badge.value.title()} Badge).

    Benefits included:
    """
    for b in benefits:
        body += f"\n- {b}"

    body += "\n\nThank you for choosing Medilogic! Keep your profile up-to-date to get more visibility."

    # Send the email
    send_email(to_email=to_email, subject=subject, body=body)