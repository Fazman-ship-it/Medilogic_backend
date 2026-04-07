import stripe
import os
from fastapi import Request
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app import models
import stripe
import os
from app.utilites.time_utilities import now_utc,to_local,to_utc
from datetime import datetime, timedelta, timezone
router = APIRouter()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
endpoint_secret = os.getenv("STRIPE_WEBHOOK_SECRET2")

@router.post("/billing-webhook")
async def billing_webhook(request: Request, db: Session = Depends(get_db)):

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload,
            sig_header,
            endpoint_secret
        )
    except Exception as e:
        print("❌ Webhook verification failed:", str(e))
        raise HTTPException(status_code=400, detail="Webhook error")

    event_id = event["id"]
    event_type = event["type"]
    data = event["data"]["object"]

    print("🔔 Stripe event received:", event_type)

    # ======================================================
    # 🔥 IDEMPOTENCY (PREVENT DUPLICATES)
    # ======================================================
    existing_event = db.query(models.StripeWebhookEvent).filter(
        models.StripeWebhookEvent.id == event_id
    ).first()

    if existing_event:
        print("⚠️ Duplicate webhook ignored:", event_id)
        return {"status": "duplicate"}

    db.add(models.StripeWebhookEvent(id=event_id))
    db.commit()

    # ======================================================
    # 🔥 HELPER: MAP STRIPE STATUS → YOUR ENUM
    # ======================================================
    def map_stripe_status(stripe_status: str) -> str:
        if stripe_status in ["active", "trialing"]:
            return "active"
        elif stripe_status in ["past_due", "unpaid"]:
            return "past_due"
        elif stripe_status in ["canceled"]:
            return "cancelled"
        elif stripe_status in ["incomplete", "incomplete_expired"]:
            return "inactive"
        else:
            return "inactive"

    # ======================================================
    # 1️⃣ PAYMENT SUCCEEDED
    # ======================================================
    if event_type == "invoice.payment_succeeded":

        subscription_id = data.get("subscription")

        if not subscription_id:
            return {"status": "no_subscription"}

        org = db.query(models.Organization).filter(
            models.Organization.stripe_subscription_id == subscription_id
        ).first()

        if org:
            try:
                org.subscription_status = "active"

                current_period_end = data.get("current_period_end")
                if current_period_end:
                    org.subscription_current_period_end = datetime.fromtimestamp(
                        current_period_end,
                        tz=timezone.utc
                    )

                db.commit()

                print("✅ Payment success → org activated:", org.id)

            except Exception as e:
                print("❌ Error processing payment success:", str(e))

    # ======================================================
    # 2️⃣ PAYMENT FAILED
    # ======================================================
    elif event_type == "invoice.payment_failed":

        subscription_id = data.get("subscription")

        if not subscription_id:
            return {"status": "no_subscription"}

        org = db.query(models.Organization).filter(
            models.Organization.stripe_subscription_id == subscription_id
        ).first()

        if org:
            org.subscription_status = "past_due"
            db.commit()

            print("⚠️ Payment failed → org past_due:", org.id)

    # ======================================================
    # 3️⃣ SUBSCRIPTION UPDATED
    # ======================================================
    elif event_type == "customer.subscription.updated":

        subscription_id = data.get("id")

        if not subscription_id:
            return {"status": "no_subscription"}

        org = db.query(models.Organization).filter(
            models.Organization.stripe_subscription_id == subscription_id
        ).first()

        if org:
            stripe_status = data.get("status")

            org.subscription_status = map_stripe_status(stripe_status)

            current_period_end = data.get("current_period_end")
            if current_period_end:
                org.subscription_current_period_end = datetime.fromtimestamp(
                    current_period_end,
                    tz=timezone.utc
                )

            db.commit()

            print("🔄 Subscription updated:", stripe_status)

    # ======================================================
    # 4️⃣ SUBSCRIPTION CANCELLED
    # ======================================================
    elif event_type == "customer.subscription.deleted":

        subscription_id = data.get("id")

        if not subscription_id:
            return {"status": "no_subscription"}

        org = db.query(models.Organization).filter(
            models.Organization.stripe_subscription_id == subscription_id
        ).first()

        if org:
            org.subscription_status = "cancelled"
            org.subscription_current_period_end = None

            db.commit()

            print("❌ Subscription cancelled:", org.id)

    # ======================================================
    # 5️⃣ SUBSCRIPTION CREATED
    # ======================================================
    elif event_type == "customer.subscription.created":

        subscription_id = data.get("id")

        if not subscription_id:
            return {"status": "no_subscription"}

        org = db.query(models.Organization).filter(
            models.Organization.stripe_subscription_id == subscription_id
        ).first()

        if org:
            stripe_status = data.get("status")

            org.subscription_status = map_stripe_status(stripe_status)

            current_period_end = data.get("current_period_end")
            if current_period_end:
                org.subscription_current_period_end = datetime.fromtimestamp(
                    current_period_end,
                    tz=timezone.utc
                )

            db.commit()

            print("🆕 Subscription created:", stripe_status)

    # ======================================================
    # 🔹 OPTIONAL: LOG OTHER EVENTS
    # ======================================================
    else:
        print("ℹ️ Unhandled event:", event_type)

    return {"status": "success"}