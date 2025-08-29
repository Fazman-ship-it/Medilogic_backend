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