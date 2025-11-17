# app/routes/stripe_webhook.py
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app import models
from app.schemas import SubscriptionPlan
import stripe
import os
from app.utilites.subscribe_email import send_subscription_email
from app.schemas import BadgeType
from app.utilites.time_utilities import now_utc,to_local,to_utc
from datetime import datetime, timedelta, timezone
router = APIRouter()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
endpoint_secret = os.getenv("STRIPE_WEBHOOK_SECRET")


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    # Verify Stripe webhook signature
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    # -------------------------
    # Handle successful subscription payment
    # -------------------------
    if event["type"] == "invoice.payment_succeeded":
        invoice = event["data"]["object"]
        subscription_id = invoice["subscription"]
        customer_id = invoice["customer"]

        # Find the Payment record
        payment = db.query(models.Payment).filter(
            models.Payment.reference == subscription_id,
            models.Payment.provider == "stripe"
        ).first()

        if payment and not payment.is_verified:
            payment.status = "succeeded"
            payment.is_verified = True

            # Activate subscription for the driver based on Stripe
            driver = db.query(models.Medilogic_Driver).filter(
                models.Medilogic_Driver.id == payment.medilogic_driver_id
            ).first()

            if driver:
                # Get Stripe subscription object
                stripe_subscription = stripe.Subscription.retrieve(subscription_id)
                plan_value = stripe_subscription.metadata.get("plan", SubscriptionPlan.free.value)
                stripe_status = stripe_subscription.status  # 'active', 'canceled', 'past_due', etc.

                # Update driver based purely on Stripe
                if stripe_status == "active":
                    driver.subscription_status = "active"
                    driver.subscription_plan = SubscriptionPlan(plan_value)
                    if plan_value == SubscriptionPlan.green.value:
                        driver.badge_type = BadgeType.green.value
                    elif plan_value == SubscriptionPlan.blue.value:
                        driver.badge_type = BadgeType.blue.value
                    else:
                        driver.badge_type = BadgeType.none.value
                elif stripe_status in ["cancelled", "expired"]:
                    driver.subscription_status = "cancelled"
                    driver.subscription_plan = SubscriptionPlan.free
                    driver.badge_type = BadgeType.none.value
                else:  # e.g., past_due
                    driver.subscription_status = "expired"
                    driver.subscription_plan = SubscriptionPlan.free
                    driver.badge_type = BadgeType.none.value

                # Enable features based on badge
                driver.can_upload_docs = driver.badge_type in [BadgeType.green.value, BadgeType.blue.value]
                driver.can_view_analytics = driver.badge_type in [BadgeType.green.value, BadgeType.blue.value]
                driver.can_see_org_names = driver.badge_type == BadgeType.blue.value

                # Send subscription confirmation email
                send_subscription_email(
                    to_email=driver.email,
                    full_name=driver.name,
                    badge=driver.badge_type,
                    plan=driver.subscription_plan
                )

                db.commit()

    return {"status": "success"}

# app/routes/stripe_webhook.py
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
import stripe
from app.config import settings
from app import models, database
from datetime import datetime
from app.utilites.time_utilities import now_utc,to_local,to_utc
stripe.api_key = settings.STRIPE_SECRET_KEY

WEBHOOK_SECRET = settings.STRIPE_WEBHOOK_SECRET


@router.post("/webhook/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(database.get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Webhook error: {str(e)}")

    event_type = event["type"]
    data = event["data"]["object"]

    # ✅ 1. One-time application fee
    if event_type == "checkout.session.completed":
        metadata = data.get("metadata", {})
        payment_id = metadata.get("payment_id")
        application_id = metadata.get("application_id")

        if payment_id and application_id:
            payment = db.query(models.Payment).filter_by(id=payment_id).first()
            application = db.query(models.InternationalApplication).filter_by(id=application_id).first()

            if payment and application:
                payment.status = "succeeded"
                payment.is_verified = True
                payment.amount = data.get("amount_total", 0) / 100.0
                payment.currency = data.get("currency", "gbp")
                payment.paid_at = now_utc()

                application.has_paid_application_fee = True
                application.application_fee_payment_id = payment.id  # ✅ Link to application
                db.commit()

    # ✅ 2. Subscription created
    elif event_type == "customer.subscription.created":
        subscription_id = data["id"]
        customer_id = data["customer"]
        status = data["status"]
        price_id = data["items"]["data"][0]["price"]["id"]

        application = db.query(models.InternationalApplication).filter_by(
            stripe_customer_id=customer_id
        ).first()
        if application:
            application.stripe_subscription_id = subscription_id
            application.subscription_status = models.SubscriptionStatus(status)  # ✅ Enum mapping
            application.subscription_start_date = datetime.fromtimestamp(data["start_date"],tz=timezone.utc)
            application.subscription_end_date = datetime.fromtimestamp(data["current_period_end"],tz=timezone.utc)
            application.badge_type = (
                models.BadgeType.green if price_id == settings.STRIPE_GREEN_PRICE_ID
                else models.BadgeType.blue
            )
            application.stripe_price_id = price_id
            db.commit()

    # ✅ 3. Subscription updated
    elif event_type == "customer.subscription.updated":
        subscription_id = data["id"]
        status = data["status"]
        price_id = data["items"]["data"][0]["price"]["id"]

        application = db.query(models.InternationalApplication).filter_by(
            stripe_subscription_id=subscription_id
        ).first()
        if application:
            application.subscription_status = models.SubscriptionStatus(status)  # ✅ Enum mapping
            application.subscription_end_date = datetime.fromtimestamp(data["current_period_end"], tz=timezone.utc)
            application.badge_type = (
                models.BadgeType.green if price_id == settings.STRIPE_GREEN_PRICE_ID
                else models.BadgeType.blue
            )
            application.stripe_price_id = price_id
            db.commit()

    # ✅ 4. Subscription canceled
    elif event_type == "customer.subscription.deleted":
        subscription_id = data["id"]
        application = db.query(models.InternationalApplication).filter_by(
            stripe_subscription_id=subscription_id
        ).first()
        if application:
            application.subscription_status = models.SubscriptionStatus.cancelled
            application.subscription_end_date = now_utc()
            application.badge_type = models.BadgeType.none
            db.commit()

    # ✅ 5. Payment failure
    elif event_type == "invoice.payment_failed":
        subscription_id = data.get("subscription")
        if subscription_id:
            application = db.query(models.InternationalApplication).filter_by(
                stripe_subscription_id=subscription_id
            ).first()
            if application:
                application.subscription_status = models.SubscriptionStatus.expired
                db.commit()

    return {"status": "success"}