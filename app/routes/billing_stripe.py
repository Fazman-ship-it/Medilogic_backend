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

    event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)

    event_id = event["id"]
    event_type = event["type"]
    data = event["data"]["object"]

    existing_event = db.query(models.StripeWebhookEvent).filter(
        models.StripeWebhookEvent.id == event_id
    ).first()

    if existing_event:
        return {"status": "duplicate"}

    db.add(models.StripeWebhookEvent(id=event_id))
    db.commit()

    def map_status(s):
        if s in ["active", "trialing"]:
            return "active"
        elif s in ["past_due", "unpaid"]:
            return "past_due"
        elif s in ["canceled"]:
            return "cancelled"
        return "inactive"

    subscription_id = data.get("id") or data.get("subscription")

    if not subscription_id:
        return {"status": "no_subscription"}

    subscription = db.query(models.Subscription).filter(
        models.Subscription.stripe_subscription_id == subscription_id
    ).first()

    if not subscription:
        return {"status": "not_found"}

    if "status" in data:
        subscription.status = map_status(data.get("status"))

    if data.get("current_period_end"):
        subscription.current_period_end = datetime.fromtimestamp(
            data.get("current_period_end"),
            tz=timezone.utc
        )

    db.commit()

    return {"status": "updated"}