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
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")  # whsec_...

def apply_plan_features(driver: models.Medilogic_Driver, plan: schemas.SubscriptionPlan):
    """Keep your feature toggles in one place."""
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
        # Invalid payload
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        # Invalid signature
        raise HTTPException(status_code=400, detail="Invalid signature")

    event_type = event["type"]
    data_obj = event["data"]["object"]

    # ----------------------------
    # 1) Invoice paid -> ACTIVE
    # ----------------------------
    if event_type == "invoice.payment_succeeded":
        subscription_id = data_obj.get("subscription")
        customer_id = data_obj.get("customer")

        driver = None
        if subscription_id:
            driver = db.query(models.Medilogic_Driver).filter(
                models.Medilogic_Driver.stripe_subscription_id == subscription_id
            ).first()

        if not driver and customer_id:
            driver = db.query(models.Medilogic_Driver).filter(
                models.Medilogic_Driver.stripe_customer_id == customer_id
            ).first()

        if driver:
            driver.subscription_status = schemas.SubscriptionStatus.active
            driver.subscription_start = driver.subscription_start or now_utc()
            driver.subscription_end = None
            db.commit()

        return {"ok": True}

    # ----------------------------
    # 2) Invoice failed -> EXPIRED (or NONE)
    # ----------------------------
    if event_type == "invoice.payment_failed":
        subscription_id = data_obj.get("subscription")
        customer_id = data_obj.get("customer")

        driver = None
        if subscription_id:
            driver = db.query(models.Medilogic_Driver).filter(
                models.Medilogic_Driver.stripe_subscription_id == subscription_id
            ).first()

        if not driver and customer_id:
            driver = db.query(models.Medilogic_Driver).filter(
                models.Medilogic_Driver.stripe_customer_id == customer_id
            ).first()

        if driver:
            driver.subscription_status = schemas.SubscriptionStatus.expired
            db.commit()

        return {"ok": True}

    # ----------------------------
    # 3) Subscription deleted -> CANCELLED + FREE
    # ----------------------------
    if event_type == "customer.subscription.deleted":
        subscription_id = data_obj.get("id")
        customer_id = data_obj.get("customer")

        driver = db.query(models.Medilogic_Driver).filter(
            models.Medilogic_Driver.stripe_subscription_id == subscription_id
        ).first()

        if not driver and customer_id:
            driver = db.query(models.Medilogic_Driver).filter(
                models.Medilogic_Driver.stripe_customer_id == customer_id
            ).first()

        if driver:
            driver.subscription_status = schemas.SubscriptionStatus.cancelled
            driver.subscription_end = now_utc()

            # move to free & lock features
            apply_plan_features(driver, schemas.SubscriptionPlan.free)

            driver.stripe_subscription_id = None
            driver.stripe_price_id = None
            driver.cancel_at_period_end = False
            db.commit()

        return {"ok": True}

    # Optional: handle subscription.updated if you want
    # if event_type == "customer.subscription.updated": ...

    return {"ok": True, "ignored": event_type}