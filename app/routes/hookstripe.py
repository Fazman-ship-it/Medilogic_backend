import os
import stripe
from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.models import BadgeType
from app.utilites.time_utilities import now_utc

router = APIRouter(prefix="/hookstripe", tags=["Hookstripe"])

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")


def apply_plan_features(driver: models.Medilogic_Driver, plan: schemas.SubscriptionPlan):
    """Centralised feature activation"""
    driver.subscription_plan = plan

    if plan == schemas.SubscriptionPlan.green:
        driver.badge_type = BadgeType.green.value
        driver.can_upload_docs = True
        driver.can_view_analytics = True
        driver.can_see_org_names = False

    elif plan == schemas.SubscriptionPlan.blue:
        driver.badge_type = BadgeType.blue.value
        driver.can_upload_docs = True
        driver.can_view_analytics = True
        driver.can_see_org_names = True

    else:  # free
        driver.badge_type = BadgeType.none.value
        driver.can_upload_docs = False
        driver.can_view_analytics = False
        driver.can_see_org_names = False


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):

    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=500, detail="STRIPE_WEBHOOK_SECRET not set")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig_header,
            secret=STRIPE_WEBHOOK_SECRET,
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    event_type = event["type"]
    data_obj = event["data"]["object"]

    # ==========================================================
    # 1️⃣ PAYMENT SUCCEEDED → ACTIVATE SUBSCRIPTION
    # ==========================================================
    if event_type == "invoice.payment_succeeded":

        subscription_id = data_obj.get("subscription")

        driver = db.query(models.Medilogic_Driver).filter(
            models.Medilogic_Driver.stripe_subscription_id == subscription_id
        ).first()

        if driver:

            driver.subscription_status = schemas.SubscriptionStatus.active
            driver.subscription_start = now_utc()
            driver.subscription_end = None

            # Determine plan from Stripe price
            if driver.stripe_price_id == os.getenv("STRIPE_GREEN_PRICE_ID"):
                apply_plan_features(driver, schemas.SubscriptionPlan.green)

            elif driver.stripe_price_id == os.getenv("STRIPE_BLUE_PRICE_ID"):
                apply_plan_features(driver, schemas.SubscriptionPlan.blue)

            db.commit()

        return {"status": "activated"}

    # ==========================================================
    # 2️⃣ PAYMENT FAILED → MARK EXPIRED
    # ==========================================================
    if event_type == "invoice.payment_failed":

        subscription_id = data_obj.get("subscription")

        driver = db.query(models.Medilogic_Driver).filter(
            models.Medilogic_Driver.stripe_subscription_id == subscription_id
        ).first()

        if driver:
            driver.subscription_status = schemas.SubscriptionStatus.expired
            db.commit()

        return {"status": "payment_failed"}

    # ==========================================================
    # 3️⃣ SUBSCRIPTION CANCELLED → DOWNGRADE TO FREE
    # ==========================================================
    if event_type == "customer.subscription.deleted":

        subscription_id = data_obj.get("id")

        driver = db.query(models.Medilogic_Driver).filter(
            models.Medilogic_Driver.stripe_subscription_id == subscription_id
        ).first()

        if driver:
            driver.subscription_status = schemas.SubscriptionStatus.cancelled
            driver.subscription_end = now_utc()

            # Downgrade to free
            apply_plan_features(driver, schemas.SubscriptionPlan.free)

            driver.stripe_subscription_id = None
            driver.stripe_price_id = None
            driver.cancel_at_period_end = False

            db.commit()

        return {"status": "cancelled"}

    # ==========================================================
    # Ignore other Stripe events
    # ==========================================================
    return {"status": "ignored", "event": event_type}