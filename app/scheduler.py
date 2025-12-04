from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError, PendingRollbackError
from datetime import datetime, timedelta, date
from pytz import timezone
import random
import logging
from app import models, database
from app.database import SessionLocal
from app.models import Trip, RecurrenceRule, DriverLocationHistory
from app.utilites.time_utilities import now_utc
from app.utilites.logging import log_activity
from app.utilites.delete_old_data import delete_expired_data
from app.utilites.compliance_auditor import run_compliance_audit_check
from app.notifications import send_compliance_alert
from app.compliance_scheduler import send_weekly_compliance_reports
from app.client_notification import send_client_notifications
from app.utilites.email_utilites import send_email
from app.schemas import SubscriptionPlan, SubscriptionStatus
from app.utilites.subscribe_email import send_subscription_email
from app.utilites.daily_notify import send_daily_notification_to_all
from app.utilites.optimizer_model import train_org_model
from app.driver_notification import notify_upcoming_trips
from app.retrain_location_model import train_org_model
from app.models import PendingApplication,User
from app.utilites.montly_report import generate_monthly_waste_statement,generate_monthly_waste_statement_for_org

logger = logging.getLogger(__name__)

# === JOB 1: Delete Unverified Accounts ===
def delete_unverified_accounts():
    db: Session = None
    try:
        db = SessionLocal()
        threshold_time = now_utc() - timedelta(hours=24)
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
    except (OperationalError, PendingRollbackError) as e:
        logger.error(f"Database connection issue in delete_unverified_accounts: {e}")
        if db:
            db.rollback()
    except Exception as e:
        logger.error(f"Unexpected error in delete_unverified_accounts: {e}")
    finally:
        if db:
            db.close()


# === JOB 2: Clone Recurring Trips ===
def clone_recurring_trips():
    db: Session = None
    try:
        db = SessionLocal()
        now = now_utc()
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
                    created_at=now_utc(),
                    recurrence_rule=trip.recurrence_rule
                )
                db.add(new_trip)

        db.commit()
    except (OperationalError, PendingRollbackError) as e:
        logger.error(f"Database connection issue in clone_recurring_trips: {e}")
        if db:
            db.rollback()
    finally:
        if db:
            db.close()


# === JOB 3: Update Overdue Invoices ===
def update_overdue_invoices():
    """
    Automatically mark unpaid invoices as overdue
    and notify the client + admins.
    """
    db: Session = None
    try:
        db = SessionLocal()
        today = now_utc().date()

        overdue_invoices = db.query(models.Invoice).filter(
            models.Invoice.status == "unpaid",
            models.Invoice.due_date < today
        ).all()

        if not overdue_invoices:
            return  # nothing to update

        for invoice in overdue_invoices:
            old_status = invoice.status
            invoice.status = "overdue"

            # Update updated_at timestamp if exists
            if hasattr(invoice, "updated_at"):
                invoice.updated_at = datetime.utcnow()

            # --- Fetch related records ---
            client = db.query(models.User).filter(models.User.id == invoice.client_id).first()
            org_admins = db.query(models.User).filter(
                models.User.organization_id == invoice.organization_id,
                models.User.role == "admin"
            ).all()

            # --- Send email to client ---
            if client and client.email:
                send_email(
                    client.email,
                    subject="Invoice Overdue Reminder",
                    body=f"""
Your invoice {invoice.invoice_number} is now OVERDUE.

Amount: £{invoice.amount}
Due Date: {invoice.due_date}
Status changed from {old_status} → overdue.

Please pay as soon as possible.
"""
                )

            # --- Notify admins ---
            for admin in org_admins:
                if admin.email:
                    send_email(
                        admin.email,
                        subject="Client Invoice Overdue Alert",
                        body=f"""
An invoice has become overdue.

Invoice: {invoice.invoice_number}
Client: {client.name if client else 'Unknown'}
Amount: £{invoice.amount}
Due Date: {invoice.due_date}

Please take action.
"""
                    )

            # --- Activity Logging ---
            log_activity(
                db=db,
                user_id=None,  # system-generated action
                action="invoice_marked_overdue",
                details=f"Auto-updated invoice {invoice.invoice_number} to overdue",
            )

        db.commit()
        print(f"[Scheduler] Marked {len(overdue_invoices)} invoices as OVERDUE.")

    except Exception as e:
        if db:
            db.rollback()
        logger.error(f"[Scheduler Error] update_overdue_invoices: {e}")

    finally:
        if db:
            db.close()

# === JOB 4: Clean up old location logs ===
def cleanup_old_location_logs():
    db = None
    try:
        db = SessionLocal()
        cutoff = now_utc() - timedelta(days=30)
        db.query(DriverLocationHistory).filter(
            DriverLocationHistory.timestamp < cutoff
        ).delete()
        db.commit()
    except (OperationalError, PendingRollbackError) as e:
        logger.error(f"Database issue in cleanup_old_location_logs: {e}")
        if db:
            db.rollback()
    finally:
        if db:
            db.close()


# === JOB 5: Retrain Location Model ===
def scheduled_retrain_job():
    print(f"🔁 Retraining all org models at {now_utc().strftime('%Y-%m-%d %H:%M:%S')}")
    try:
        retrain_all_org_models()
    except Exception as e:
        print(f"❌ Error during scheduled retraining: {e}")

# === JOB 6: Daily Compliance Audit ===
def audit_compliance_job():
    db: Session = None
    try:
        db = SessionLocal()
        flagged_orgs = run_compliance_audit_check(db)
        for org in flagged_orgs:
            reason = org.get("reason", "Unspecified reason")
            org_id = org.get("organization_id")
            send_compliance_alert(org_id=org_id, reason=reason)
        print(f"[Compliance Audit] {len(flagged_orgs)} orgs flagged.")
    except (OperationalError, PendingRollbackError) as e:
        logger.error(f"Database issue in audit_compliance_job: {e}")
        if db:
            db.rollback()
    finally:
        if db:
            db.close()


# === JOB 7: Expire Badges ===
def expire_badges():
    db: Session = None
    try:
        db = SessionLocal()
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

            user = db.query(models.User).filter(models.User.id == app.user_id).first()
            if user and user.email:
                send_email(
                    to_email=user.email,
                    subject="Your Medilogic Verification Badge Has Expired",
                    body=(
                        f"Hello {user.full.name or 'User'},\n\n"
                        "Your Medilogic verification badge subscription has expired. "
                        "To continue enjoying higher visibility and analytics, please renew.\n\n"
                        "Best regards,\nThe Medilogic Team"
                    )
                )
            print(f"Downgraded {app.user_id} to no badge (expired)")
        db.commit()
    except (OperationalError, PendingRollbackError) as e:
        logger.error(f"Database issue in expire_badges: {e}")
        if db:
            db.rollback()
    finally:
        if db:
            db.close()


# === JOB 8: Daily Notification ===
def pick_and_send_daily_notification():
    db: Session = None
    try:
        db = SessionLocal()
        db.query(models.DailyNotification).update({models.DailyNotification.is_active_today: False})
        db.commit()

        all_notifications = db.query(models.DailyNotification).all()
        if not all_notifications:
            print("⚠️ No notifications found.")
            return

        chosen = random.choice(all_notifications)
        chosen.is_active_today = True
        db.commit()
        db.refresh(chosen)
        send_daily_notification_to_all(db, chosen.subject, chosen.body)
        print(f"✅ Sent daily notification: {chosen.subject}")
    except (OperationalError, PendingRollbackError) as e:
        logger.error(f"Database issue in pick_and_send_daily_notification: {e}")
        if db:
            db.rollback()
    finally:
        if db:
            db.close()


# === JOB 9: Retrain Optimizer Models ===
def retrain_all_org_models():
    db: Session = None
    try:
        db = SessionLocal()
        orgs = db.query(models.Organization).all()
        for org in orgs:
            model = train_org_model(db, str(org.id))
            if model:
                print(f"[Scheduler] ✅ Retrained optimizer model for org {org.organization_name} ({org.id})")
            else:
                print(f"[Scheduler] ⚠️ Skipped org {org.organization_name} ({org.id}) - insufficient data")
    finally:
        if db:
            db.close()

# === JOB 10: Auto-manage Incidents ===
def auto_manage_incidents():
    """
    Daily incident management:
    1️⃣ Auto-close resolved incidents > 7 days old.
    2️⃣ Notify admins if pending > 5 days.
    3️⃣ Notify regulators if critical unresolved > 3 days.
    """
    db: Session = SessionLocal()
    today = datetime.utcnow()

    try:
        # 1️⃣ Auto-close resolved incidents older than 7 days
        seven_days_ago = today - timedelta(days=7)
        to_close = db.query(models.Incident)\
            .filter(models.Incident.status == "resolved")\
            .filter(models.Incident.updated_at < seven_days_ago)\
            .all()

        for incident in to_close:
            incident.status = "closed"
            db.commit()
            log_activity(db, user_id=None, action="incident_auto_closed",
                         details=f"Incident {incident.id} auto-closed after 7 days")
        
        # 2️⃣ Notify admins for pending incidents older than 5 days
        five_days_ago = today - timedelta(days=5)
        pending_admin_notify = db.query(models.Incident)\
            .filter(models.Incident.status == "pending")\
            .filter(models.Incident.created_at < five_days_ago)\
            .all()

        for incident in pending_admin_notify:
            admin_emails = [admin.email for admin in db.query(models.User)
                            .filter(models.User.organization_id == incident.organization_id,
                                    models.User.role == "admin",
                                    models.User.is_active == True,
                                    models.User.email.isnot(None)).all()]
            if admin_emails:
                subject = f"⏰ Incident Pending Alert: {incident.title}"
                body = f"The incident '{incident.title}' has been pending for more than 5 days."
                send_email(subject, body, admin_emails)
                log_activity(db, user_id=None, action="incident_pending_notification",
                             details=f"Admins notified for pending incident {incident.id}")

        # 3️⃣ Notify regulators for critical unresolved incidents > 3 days
        three_days_ago = today - timedelta(days=3)
        critical_incidents = db.query(models.Incident)\
            .filter(models.Incident.severity == "critical")\
            .filter(models.Incident.status != "resolved")\
            .filter(models.Incident.created_at < three_days_ago)\
            .all()

        for incident in critical_incidents:
            regulators = db.query(models.User)\
                .filter(models.User.role == "regulator",
                        models.User.is_active == True,
                        models.User.email.isnot(None))\
                .all()
            regulator_emails = [r.email for r in regulators if r.email]

            if regulator_emails:
                subject = f"🚨 Critical Unresolved Incident: {incident.title}"
                body = f"The critical incident '{incident.title}' has not been resolved for more than 3 days."
                send_email(subject, body, regulator_emails)
                log_activity(db, user_id=None, action="critical_incident_notification",
                             details=f"Regulators notified for incident {incident.id}")

    except Exception as e:
        print(f"⚠️ Error in auto_manage_incidents: {e}")
        db.rollback()
    finally:
        db.close()

def send_upcoming_due_reminders():
    """
    Automatically sends email reminders 2 days before invoice due date.
    Notifies:
    - Client
    - Organization admins
    Logs activity for auditing.
    """
    db: Session = None
    try:
        db = SessionLocal()
        reminder_date = now_utc().date() + timedelta(days=2)

        upcoming_invoices = db.query(models.Invoice).filter(
            models.Invoice.status == "unpaid",
            models.Invoice.due_date == reminder_date
        ).all()

        if not upcoming_invoices:
            return  # nothing to do

        for invoice in upcoming_invoices:
            client = db.query(models.User).filter(models.User.id == invoice.client_id).first()
            org_admins = db.query(models.User).filter(
                models.User.organization_id == invoice.organization_id,
                models.User.role == "admin"
            ).all()

            # --- Email client ---
            if client and client.email:
                send_email(
                    client.email,
                    subject="Upcoming Invoice Due Reminder",
                    body=f"""
Dear {client.name},

Your invoice {invoice.invoice_number} is due in 2 days.

Amount: £{invoice.amount}
Due Date: {invoice.due_date}

Please ensure payment is made on time.
"""
                )

            # --- Notify admins ---
            for admin in org_admins:
                if admin.email:
                    send_email(
                        admin.email,
                        subject="Client Invoice Upcoming Due Reminder",
                        body=f"""
Invoice {invoice.invoice_number} for client {client.name if client else 'Unknown'} is due in 2 days.

Amount: £{invoice.amount}
Due Date: {invoice.due_date}
"""
                    )

            # --- Activity Logging ---
            log_activity(
                db=db,
                user_id=None,  # system-generated
                action="invoice_upcoming_due_reminder",
                details=f"Reminder sent for invoice {invoice.invoice_number}, due {invoice.due_date}",
            )

    except Exception as e:
        if db:
            db.rollback()
        logger.error(f"[Scheduler Error] send_upcoming_due_reminders: {e}")
    finally:
        if db:
            db.close()
            

def cleanup_pending_applications():
    """
    Deletes:
    1. Applications that have been registered (exist in User table).
    2. Pending applications older than 30 days.
    """
    db: Session = None
    try:
        db = SessionLocal()
        now = datetime.utcnow()
        cutoff_date = now - timedelta(days=30)

        # 1️⃣ Delete applications already registered
        registered_emails = [u.email for u in db.query(User.email).all()]
        apps_to_delete_registered = db.query(PendingApplication).filter(
            PendingApplication.email.in_(registered_emails)
        ).all()

        for app in apps_to_delete_registered:
            db.delete(app)
            log_activity(
                db=db,
                user_id=None,
                action="pending_application_deleted",
                details=f"Deleted application {app.email} because user already registered."
            )

        # 2️⃣ Delete applications older than 30 days still pending
        old_pending_apps = db.query(PendingApplication).filter(
            PendingApplication.status == "pending",
            PendingApplication.submitted_at < cutoff_date
        ).all()

        for app in old_pending_apps:
            db.delete(app)
            log_activity(
                db=db,
                user_id=None,
                action="pending_application_deleted",
                details=f"Deleted old pending application {app.email} submitted on {app.submitted_at}."
            )

        db.commit()
        print(f"[Scheduler] Deleted {len(apps_to_delete_registered) + len(old_pending_apps)} pending applications.")

    except Exception as e:
        if db:
            db.rollback()
        logger.error(f"[Scheduler Error] cleanup_pending_applications: {e}")

    finally:
        if db:
            db.close()

def monthly_waste_statement_job():
    db: Session = SessionLocal()
    today = datetime.utcnow()
    year = today.year
    month = today.month - 1 if today.month > 1 else 12
    year = year - 1 if month == 12 else year

    import asyncio
    asyncio.run(generate_monthly_waste_statement(db, year, month))
    db.close()
    

def monthly_org_report_job():
    db: Session = SessionLocal()
    today = datetime.utcnow()
    year = today.year
    month = today.month - 1 if today.month > 1 else 12
    year = year - 1 if month == 12 else year

    import asyncio
    asyncio.run(generate_monthly_waste_statement_for_org(db, year, month))
    db.close()    

# === Initialize Scheduler ===
scheduler = BackgroundScheduler(timezone=timezone("Europe/London"))

# === Add Scheduled Jobs ===
scheduler.add_job(delete_unverified_accounts, CronTrigger(hour=3, minute=0), id="delete_unverified_accounts", replace_existing=True)
scheduler.add_job(delete_expired_data, trigger="cron", hour=2, id="delete_expired_data")
scheduler.add_job(clone_recurring_trips, trigger="interval", days=1, id="clone_recurring_trips")
scheduler.add_job(notify_upcoming_trips, "interval", minutes=5, id="trip_reminder_checker", replace_existing=True)
scheduler.add_job(send_client_notifications, trigger="cron", minute="*/15", id="notify_clients")
scheduler.add_job(update_overdue_invoices, trigger="cron", hour=2, minute=0, id="update_overdue_invoices")
scheduler.add_job(send_weekly_compliance_reports, trigger="cron", day_of_week="mon", hour=9, minute=0, id="weekly_compliance_report")
scheduler.add_job(cleanup_old_location_logs, trigger="cron", day_of_week="sun", hour=3, minute=0, id="cleanup_old_location_logs")
scheduler.add_job(scheduled_retrain_job, trigger=IntervalTrigger(hours=6), id="retrain_location_model_job", replace_existing=True)
scheduler.add_job(audit_compliance_job, trigger=IntervalTrigger(days=1), id="daily_compliance_audit")
scheduler.add_job(expire_badges, trigger="cron", hour=0, minute=0, id="expire_badges")
scheduler.add_job(pick_and_send_daily_notification, trigger="cron", hour=6, minute=0, id="daily_pick_notification")
scheduler.add_job(retrain_all_org_models, trigger=IntervalTrigger(days=1), id="daily_optimizer_retrain", replace_existing=True)
scheduler.add_job(auto_manage_incidents, trigger="cron", hour=2, minute=0, id="auto_manage_incidents", replace_existing=True)
scheduler.add_job(send_upcoming_due_reminders, trigger="cron", hour=9, minute=0, id="send_upcoming_due_reminders")
scheduler.add_job(cleanup_pending_applications, trigger="cron", hour=3, minute=0, id="cleanup_pending_applications")
scheduler.add_job(monthly_waste_statement_job, trigger="cron",day=1,hour=8,minute=0,id="monthly_waste_statement",replace_existing=True)
scheduler.add_job(monthly_waste_statement_job, trigger="cron", day=1, hour=8, minute=0, id="monthly_org_report", replace_existing=True)

# === Start Scheduler ===
def start_scheduler():
    scheduler.start()
    print("[Scheduler] Started.")