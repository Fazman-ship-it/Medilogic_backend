from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from app.models import Trip, RecurrenceRule
from app.database import SessionLocal
from app import models
from pytz import timezone
from app.compliance_scheduler import send_weekly_compliance_reports
from app.client_notification import send_client_notifications
from app.utilites.logging import log_activity
from apscheduler.triggers.cron import CronTrigger
from app.driver_notification import notify_upcoming_trips
from app.utilites.delete_old_data import delete_expired_data
from datetime import datetime, timedelta
from app.database import SessionLocal
from app.models import DriverLocationHistory
from app.retrain_location_model import retrain_location_model
from apscheduler.triggers.interval import IntervalTrigger
from app.utilites.compliance_auditor import run_compliance_audit_check
from app.notifications import send_compliance_alert
from datetime import date
from app import database
from app.utilites.email_utilites import send_email
from app.schemas import SubscriptionPlan, SubscriptionStatus
from app.utilites.driver_subscription_utilities import start_subscription
from app.utilites.subscribe_email import send_subscription_email  # utility to send emails
from app.models import Medilogic_Driver
import random
from app.utilites.daily_notify import send_daily_notification_to_all

# === JOB 1: Delete Unverified Accounts ===
def delete_unverified_accounts():
    db: Session = SessionLocal()
    try:
        threshold_time = datetime.utcnow() - timedelta(hours=24)
        unverified_users = db.query(models.User).filter(
            models.User.is_verified == False,
            models.User.email_verification_token.isnot(None),
            models.User.token_expires_at < threshold_time
        ).all()

        for user in unverified_users:
            log_activity(
                db=db,
                user_id=user.id,
                action="auto_delete_unverified_account",
                details=f"Deleted unverified account {user.email} after 24h expiration"
            )
            db.delete(user)

        db.commit()
        print(f"[CLEANUP] Deleted {len(unverified_users)} unverified accounts")
    except Exception as e:
        print(f"❌ Error deleting unverified accounts: {e}")
    finally:
        db.close()


# === JOB 2: Clone Recurring Trips ===
def clone_recurring_trips():
    db: Session = SessionLocal()
    try:
        now = datetime.utcnow()
        recurring_trips = db.query(Trip).filter(Trip.recurrence_rule != RecurrenceRule.none).all()

        for trip in recurring_trips:
            if trip.recurrence_rule == RecurrenceRule.weekly:
                next_date = trip.scheduled_time + timedelta(weeks=1)
            elif trip.recurrence_rule == RecurrenceRule.monthly:
                next_date = trip.scheduled_time + timedelta(weeks=4)
            else:
                continue

            existing = db.query(Trip).filter(
                Trip.scheduled_time == next_date,
                Trip.client_name == trip.client_name,
                Trip.driver_id == trip.driver_id,
                Trip.pickup_location == trip.pickup_location,
                Trip.dropoff_location == trip.dropoff_location
            ).first()

            if not existing:
                new_trip = Trip(
                    driver_id=trip.driver_id,
                    delivery_type=trip.delivery_type,
                    scheduled_time=next_date,
                    cost=trip.cost,
                    client_name=trip.client_name,
                    pickup_location=trip.pickup_location,
                    dropoff_location=trip.dropoff_location,
                    distance_km=trip.distance_km,
                    status="scheduled",
                    created_at=datetime.utcnow(),
                    recurrence_rule=trip.recurrence_rule
                )
                db.add(new_trip)

        db.commit()
    finally:
        db.close()


# === JOB 3: Update Overdue Invoices ===
def update_overdue_invoices():
    db: Session = SessionLocal()
    try:
        today = datetime.utcnow().date()
        overdue_invoices = db.query(models.Invoice).filter(
            models.Invoice.status == "unpaid",
            models.Invoice.due_date < today
        ).all()

        for invoice in overdue_invoices:
            invoice.status = "overdue"

        if overdue_invoices:
            print(f"[Scheduler] Updated {len(overdue_invoices)} overdue invoices.")

        db.commit()
    except Exception as e:
        print(f"[Scheduler] Error updating overdue invoices: {e}")
    finally:
        db.close()

#Job 4 Clean up function
def cleanup_old_location_logs():
    db = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(days=30)
        db.query(DriverLocationHistory).filter(
            DriverLocationHistory.timestamp < cutoff
        ).delete()
        db.commit()
    finally:
        db.close()
        
# Define the retrain job
def scheduled_retrain_job():
    print(f"🔁 Retraining check at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    try:
        retrain_location_model()
    except Exception as e:
        print(f"❌ Error during scheduled retraining: {e}")
        
# === 1. Daily Compliance Audit ===
def audit_compliance_job():
    db: Session = SessionLocal()
    try:
        flagged_orgs = run_compliance_audit_check(db)

        for org in flagged_orgs:
            reason = org.get("reason", "Unspecified reason")
            org_id = org.get("organization_id")

            # Central alert handling (email + app)
            send_compliance_alert(org_id=org_id, reason=reason)

        print(f"[Compliance Audit] {len(flagged_orgs)} orgs flagged.")
    finally:
        db.close() 
        
# === JOB 5: Expire Badges ===
def expire_badges():
    db: Session = database.SessionLocal()
    try:
        today = date.today()
        expired_users = (
            db.query(models.InternationalApplication)
            .filter(
                models.InternationalApplication.subscription_end_date != None,
                models.InternationalApplication.subscription_end_date < today
            )
            .all()
        )

        for app in expired_users:
            app.badge_type = models.BadgeType.none
            app.subscription_end_date = None

            # 👇 fetch user email
            user = db.query(models.User).filter(models.User.id == app.user_id).first()
            if user and user.email:
                send_email(
                    to_email=user.email,
                    subject="Your Medilogic Verification Badge Has Expired",
                    body=(
                        f"Hello {user.full_name or 'User'},\n\n"
                        "Your Medilogic verification badge subscription has expired. "
                        "To continue enjoying higher visibility and application analytics, "
                        "please renew your subscription.\n\n"
                        "🔗 Login to your dashboard to renew.\n\n"
                        "Best regards,\n"
                        "The Medilogic Team"
                    )
                )

            print(f"Downgraded {app.user_id} to no badge (expired)")
        db.commit()
    finally:
        db.close()

#== JOB 6: Renew Subscriptions ===
def renew_subscriptions():
    db: Session = SessionLocal()
    try:
        now = datetime.utcnow()
        # Find active subscriptions expiring within 1 day
        drivers = db.query(Medilogic_Driver).filter(
            Medilogic_Driver.subscription_status == SubscriptionStatus.active,
            Medilogic_Driver.subscription_end <= now + timedelta(days=1),
            Medilogic_Driver.subscription_plan.in_([SubscriptionPlan.green, SubscriptionPlan.blue])
        ).all()

        for medilogic_driver in drivers:
            # Use start_subscription to renew with prorated logic
            start_subscription(medilogic_driver, medilogic_driver.subscription_plan, months=1)
            db.commit()
            # Optional: send email notifying renewal
            send_subscription_email(
                to_email=medilogic_driver.email,
                full_name=medilogic_driver.name,
                badge=medilogic_driver.badge_type,
                plan=medilogic_driver.subscription_plan,
                renewed=True
            )
            print(f"Auto-renewed subscription for Medilogic driver {medilogic_driver.id} ({medilogic_driver.email})")

    finally:
        db.close()

#Daily notification

def pick_and_send_daily_notification():
    db: Session = SessionLocal()
    try:
        # Reset all notifications
        db.query(models.DailyNotification).update({models.DailyNotification.is_active_today: False})
        db.commit()

        # Pick a random notification (any manual or AI-generated)
        all_notifications = db.query(models.DailyNotification).all()
        if not all_notifications:
            print("⚠️ No notifications found.")
            return

        chosen = random.choice(all_notifications)
        chosen.is_active_today = True
        db.commit()
        db.refresh(chosen)

        # Send email to all verified users
        send_daily_notification_to_all(db, chosen.subject, chosen.body)

        print(f"✅ Sent daily notification: {chosen.subject}")

    finally:
        db.close()

# === Initialize Scheduler ===
scheduler = BackgroundScheduler(timezone=timezone("Europe/London"))

# === Add Scheduled Jobs ===

# 1. Delete unverified users daily at 3 AM UTC
scheduler.add_job(
    delete_unverified_accounts,
    CronTrigger(hour=3, minute=0),
    id="delete_unverified_accounts",
    replace_existing=True
)

# 2. Cleanup expired data daily at 2 AM
scheduler.add_job(
    delete_expired_data,
    trigger="cron",
    hour=2,
    id="delete_expired_data"
)

# 3. Clone recurring trips daily
scheduler.add_job(
    clone_recurring_trips,
    trigger="interval",
    days=1,
    id="clone_recurring_trips"
)

# 4. Notify drivers daily at 6 AM
scheduler.add_job(
    notify_upcoming_trips,
    trigger="cron",
    hour=6,
    minute=0,
    id="notify_drivers"
)

# 5. Notify clients daily at 6 AM
scheduler.add_job(
    send_client_notifications,
    trigger="cron",
    hour=6,
    minute=0,
    id="notify_clients"
)

# 6. Update overdue invoices daily at 2 AM
scheduler.add_job(
    update_overdue_invoices,
    trigger="cron",
    hour=2,
    minute=0,
    id="update_overdue_invoices"
)

# 7. Send weekly compliance reports every Monday at 9 AM UK time
scheduler.add_job(
    send_weekly_compliance_reports,
    trigger="cron",
    day_of_week="mon",
    hour=9,
    minute=0,
    id="weekly_compliance_report"
)
# 8. Clean up old driver location logs every Sunday at 3 AM UK time
scheduler.add_job(
    cleanup_old_location_logs,
    trigger="cron",
    day_of_week="sun",
    hour=3,
    minute=0,
    id="cleanup_old_location_logs"
)


# 9. 🔁 Run every 6 hours (or change as needed)
scheduler.add_job(
    scheduled_retrain_job,
    trigger=IntervalTrigger(hours=6),
    id="retrain_location_model_job",
    replace_existing=True,
)
# 9.audit complaince
scheduler.add_job(
    audit_compliance_job,
    trigger=IntervalTrigger(days=1),
    id="daily_compliance_audit"
)
# 10. Expire badges daily at midnight
scheduler.add_job(
    expire_badges,
    trigger="cron",
    hour=0,
    minute=0,
    id="expire_badges"
)
# 11. Renew subscriptions daily at 1 AM
scheduler.add_job(
    renew_subscriptions,
    trigger="cron",
    hour=1,
    minute=0,
    id="renew_subscriptions",
    replace_existing=True
)

# Daily notification:
scheduler.add_job(
    pick_and_send_daily_notification,
    trigger="cron",
    hour=6,
    minute=0,
    id="daily_pick_notification"
)
    

# === Start Scheduler ===
def start_scheduler():
    scheduler.start()
    print("[Scheduler] Started.")


