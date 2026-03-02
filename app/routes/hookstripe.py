import os
import stripe
from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.models import BadgeType
from app.utilites.time_utilities import now_utc

from datetime import datetime, timezone

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
    # 1️⃣ PAYMENT SUCCEEDED → ACTIVATE / RENEW
    # ==========================================================
    if event_type == "invoice.payment_succeeded":

        subscription_id = data_obj.get("subscription")

        driver = db.query(models.Medilogic_Driver).filter(
            models.Medilogic_Driver.stripe_subscription_id == subscription_id
        ).first()

        if driver:

            # Extract price
            try:
                price_id = data_obj["lines"]["data"][0]["price"]["id"]
            except (KeyError, IndexError):
                price_id = None

            # Extract billing period end
            try:
                period_end_unix = data_obj["lines"]["data"][0]["period"]["end"]
                period_end = datetime.fromtimestamp(period_end_unix, tz=timezone.utc)
            except (KeyError, IndexError):
                period_end = None

            driver.subscription_status = schemas.SubscriptionStatus.active
            driver.subscription_start = now_utc()
            driver.subscription_end = period_end
            driver.stripe_price_id = price_id
            driver.cancel_at_period_end = False

            # Restore premium features
            if price_id == os.getenv("STRIPE_GREEN_PRICE_ID"):
                apply_plan_features(driver, schemas.SubscriptionPlan.green)
            elif price_id == os.getenv("STRIPE_BLUE_PRICE_ID"):
                apply_plan_features(driver, schemas.SubscriptionPlan.blue)

            db.commit()

        return {"status": "activated_or_renewed"}


    # ==========================================================
    # 2️⃣ PAYMENT FAILED → MARK PAST_DUE + REMOVE PREMIUM
    # ==========================================================
    if event_type == "invoice.payment_failed":

        subscription_id = data_obj.get("subscription")

        driver = db.query(models.Medilogic_Driver).filter(
            models.Medilogic_Driver.stripe_subscription_id == subscription_id
        ).first()

        if driver:
            driver.subscription_status = schemas.SubscriptionStatus.past_due

            # Immediately remove premium access
            apply_plan_features(driver, schemas.SubscriptionPlan.free)

            db.commit()

        return {"status": "payment_failed_downgraded_to_free"}


    # ==========================================================
    # 3️⃣ SUBSCRIPTION UPDATED → FULL STRIPE SYNC
    # ==========================================================
    if event_type == "customer.subscription.updated":

        subscription_id = data_obj.get("id")

        driver = db.query(models.Medilogic_Driver).filter(
            models.Medilogic_Driver.stripe_subscription_id == subscription_id
        ).first()

        if driver:

            stripe_status = data_obj.get("status")
            cancel_at_period_end = data_obj.get("cancel_at_period_end", False)
            current_period_end_unix = data_obj.get("current_period_end")

            # Sync lifecycle state
            if stripe_status == "active":
                driver.subscription_status = schemas.SubscriptionStatus.active

                # Restore correct plan
                try:
                    price_id = data_obj["items"]["data"][0]["price"]["id"]
                    driver.stripe_price_id = price_id

                    if price_id == os.getenv("STRIPE_GREEN_PRICE_ID"):
                        apply_plan_features(driver, schemas.SubscriptionPlan.green)
                    elif price_id == os.getenv("STRIPE_BLUE_PRICE_ID"):
                        apply_plan_features(driver, schemas.SubscriptionPlan.blue)

                except (KeyError, IndexError):
                    pass

            elif stripe_status == "past_due":
                driver.subscription_status = schemas.SubscriptionStatus.past_due

                # Immediate downgrade
                apply_plan_features(driver, schemas.SubscriptionPlan.free)

            elif stripe_status in ["canceled", "unpaid"]:
                driver.subscription_status = schemas.SubscriptionStatus.cancelled
                apply_plan_features(driver, schemas.SubscriptionPlan.free)

            # Sync billing period
            if current_period_end_unix:
                driver.subscription_end = datetime.fromtimestamp(
                    current_period_end_unix,
                    tz=timezone.utc
                )

            driver.cancel_at_period_end = cancel_at_period_end

            db.commit()

        return {"status": "subscription_fully_synced"}


    # ==========================================================
    # 4️⃣ SUBSCRIPTION DELETED → DOWNGRADE TO FREE
    # ==========================================================
    if event_type == "customer.subscription.deleted":

        subscription_id = data_obj.get("id")

        driver = db.query(models.Medilogic_Driver).filter(
            models.Medilogic_Driver.stripe_subscription_id == subscription_id
        ).first()

        if driver:
            driver.subscription_status = schemas.SubscriptionStatus.cancelled
            driver.subscription_end = now_utc()

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