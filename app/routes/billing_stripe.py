import stripe
import os
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app import models
from datetime import datetime, timezone

router = APIRouter()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
endpoint_secret = os.getenv("STRIPE_WEBHOOK_SECRET2")


@router.post("/billing-webhook")
async def billing_webhook(request: Request, db: Session = Depends(get_db)):

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    # ======================================================
    # ✅ VERIFY STRIPE SIGNATURE
    # ======================================================
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except Exception as e:
        print("❌ Webhook verification failed:", str(e))
        raise HTTPException(status_code=400, detail="Webhook error")

    event_id = event["id"]
    event_type = event["type"]
    data = event["data"]["object"]

    # ======================================================
    # ✅ PREVENT DUPLICATE EVENTS (IDEMPOTENCY)
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
    # ✅ MAP STRIPE STATUS → YOUR SYSTEM STATUS
    # ======================================================
    def map_status(s):
        if s in ["active", "trialing"]:
            return "active"

        elif s in ["past_due", "unpaid"]:
            return "past_due"  # 🔥 triggers lock in your system

        elif s in ["incomplete", "incomplete_expired"]:
            return "incomplete"

        elif s == "canceled":
            return "inactive"  # 🔥 IMPORTANT: no "cancelled" anymore

        return "inactive"

    try:
        # ======================================================
        # ✅ EXTRACT SUBSCRIPTION ID SAFELY
        # ======================================================
        subscription_id = None

        if data.get("object") == "invoice":
            subscription_id = data.get("subscription")

        elif data.get("object") == "subscription":
            subscription_id = data.get("id")

        if not subscription_id:
            print(f"⚠️ No subscription for event: {event_type}")
            return {"status": "no_subscription"}

        # ======================================================
        # ✅ FIND SUBSCRIPTION IN DB
        # ======================================================
        subscription = db.query(models.Subscription).filter(
            models.Subscription.stripe_subscription_id == subscription_id
        ).first()

        if not subscription:
            print(f"⚠️ Subscription not found in DB: {subscription_id}")
            return {"status": "not_found"}

        # ======================================================
        # 🔥 SOURCE OF TRUTH → STRIPE
        # ======================================================
        stripe_sub = stripe.Subscription.retrieve(subscription_id)

        # ======================================================
        # ✅ UPDATE STATUS
        # ======================================================
        subscription.status = map_status(stripe_sub.status)

        # ======================================================
        # ✅ UPDATE BILLING PERIOD
        # ======================================================
        period_end_ts = stripe_sub.get("current_period_end")

        subscription.current_period_end = (
            datetime.fromtimestamp(period_end_ts, tz=timezone.utc)
            if period_end_ts
            else None
        )

        db.commit()

        print(f"✅ Webhook updated: {event_type} → {stripe_sub.status}")

        return {"status": "updated"}

    except Exception as e:
        print("🔥 Webhook FULL ERROR:", repr(e))
        return {"status": "error"}