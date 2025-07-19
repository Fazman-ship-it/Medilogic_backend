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


# === Start Scheduler ===
def start_scheduler():
    scheduler.start()
    print("[Scheduler] Started.")
