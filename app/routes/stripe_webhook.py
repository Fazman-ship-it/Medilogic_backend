# app/routes/stripe_webhook.py
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app import models
from app.utilites.driver_subscription_utilities import start_subscription
from app.schemas import SubscriptionPlan
import stripe
import os
from app.utilites.subscribe_email import send_subscription_email
router = APIRouter()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
endpoint_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

@router.post("/stripe/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    # Handle successful payment
    if event["type"] == "payment_intent.succeeded":
        intent = event["data"]["object"]
        reference = intent["id"]
        plan_value = intent["metadata"]["plan"]
        medilogic_driver_id = intent["metadata"]["medilogic_driver_id"]

        # Find payment record
        payment = db.query(models.Payment).filter(models.Payment.reference == reference).first()
        if payment and not payment.is_verified:
            payment.status = "succeeded"
            payment.is_verified = True

            # Activate subscription for driver
            driver = db.query(models.Medilogic_Driver).filter(
                models.Medilogic_Driver.id == medilogic_driver_id
            ).first()
            if driver:
                driver = start_subscription(driver, SubscriptionPlan(plan_value), months=1)
                db.commit()

                # Send subscription confirmation email
                send_subscription_email(
                    to_email=driver.email,
                    full_name=driver.name,
                    badge=driver.badge_type,
                    plan=driver.subscription_plan
                )

                # Optional: unlock features based on badge
                if driver.badge_type in ["green", "blue"]:
                    # e.g., allow document uploads
                    driver.can_upload_docs = True
                if driver.badge_type == "blue":
                    # e.g., unlock analytics dashboard and org view counts
                    driver.can_view_analytics = True
                    driver.can_see_org_names = True

                db.commit()

    return {"status": "success"}

# app/routes/stripe_webhook.py
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
import stripe
from app.config import settings
from app import models, database
from datetime import datetime

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
                payment.paid_at = datetime.utcnow()

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
            application.subscription_start_date = datetime.utcfromtimestamp(data["start_date"])
            application.subscription_end_date = datetime.utcfromtimestamp(data["current_period_end"])
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
            application.subscription_end_date = datetime.utcfromtimestamp(data["current_period_end"])
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
            application.subscription_end_date = datetime.utcnow()
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