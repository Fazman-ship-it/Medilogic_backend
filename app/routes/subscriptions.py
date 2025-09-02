from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from app import models, schemas
from app.database import get_db
from app.dependencies import get_current_user # ✅ import your JWT auth dependency
from app.config import settings
import stripe

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])

@router.post("/me/subscribe/{plan}/application-fee")
def subscribe(
    plan: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if plan not in ["green", "blue"]:
        raise HTTPException(status_code=400, detail="Invalid plan")

    # 🎯 Find the user's application
    app = db.query(models.InternationalApplication).filter(
        models.InternationalApplication.user_id == current_user.id
    ).first()

    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    # 🎯 Map plan to Stripe Price ID
    price_id = (
        settings.STRIPE_GREEN_PRICE_ID if plan == "green"
        else settings.STRIPE_BLUE_PRICE_ID
    )
    app.stripe_price_id = price_id  # save chosen plan in DB

    # 🎯 Ensure we have a Stripe Customer
    if not app.stripe_customer_id:
        customer = stripe.Customer.create(email=current_user.email)
        app.stripe_customer_id = customer.id  # save in DB

    # 🎯 Create a Checkout Session
    checkout = stripe.checkout.Session.create(
        mode="subscription",
        payment_method_types=["card"],
        customer=app.stripe_customer_id,  # ✅ use customer ID, not just email
        line_items=[{"price": price_id, "quantity": 1}],
        success_url="https://your-frontend/subscription-success?session_id={CHECKOUT_SESSION_ID}",
        cancel_url="https://your-frontend/subscription-cancel",
    )

    db.commit()  # save updates to application

    return {"checkout_url": checkout.url}

# app/routes/stripe_routes.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app import models, database
from app.dependencies import get_current_user  # adjust if path differs

@router.get("/me/subscription/application-fee")
def get_my_subscription(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    # 1️⃣ Get the user's application
    app = db.query(models.InternationalApplication).filter_by(user_id=current_user.id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    # 2️⃣ Return subscription info from the application table
    return {
        "email": current_user.email,
        "badge_type": app.badge_type.value if app.badge_type else None,
        "subscription_status": app.subscription_status.value if app.subscription_status else None,
        "stripe_customer_id": app.stripe_customer_id,
        "stripe_subscription_id": app.stripe_subscription_id,
        "stripe_price_id": app.stripe_price_id,
        "subscription_start_date": app.subscription_start_date,
        "subscription_end_date": app.subscription_end_date,
        "cancel_at_period_end": app.cancel_at_period_end,
    }
    
@router.delete("/me/subscription/application-fee")
def cancel_my_subscription(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Cancel the current user's active subscription in Stripe.
    """
    # 1️⃣ Get user's application
    app = db.query(models.InternationalApplication).filter_by(user_id=current_user.id).first()
    if not app or not app.stripe_subscription_id:
        raise HTTPException(status_code=400, detail="No active subscription found")

    try:
        # 2️⃣ Cancel subscription in Stripe immediately
        stripe.Subscription.delete(app.stripe_subscription_id)

        # 3️⃣ Update the application record
        app.subscription_status = "cancelled"  # matches your SubscriptionStatus enum
        app.cancel_at_period_end = True
        db.commit()
        db.refresh(app)

        return {"message": "Subscription canceled successfully"}
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=f"Stripe error: {str(e)}")
    
@router.post("/subscription/change/application-fee")
def change_subscription(
    badge_type: str,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Upgrade or downgrade a subscription by badge name (green/blue).
    """
    badge_type = badge_type.lower()

    if badge_type == "green":
        new_price_id = settings.STRIPE_GREEN_PRICE_ID
    elif badge_type == "blue":
        new_price_id = settings.STRIPE_BLUE_PRICE_ID
    else:
        raise HTTPException(status_code=400, detail="Invalid badge type")

    # 1️⃣ Fetch user's application
    app = db.query(models.InternationalApplication).filter_by(user_id=current_user.id).first()
    if not app or not app.stripe_subscription_id:
        raise HTTPException(status_code=400, detail="No active subscription found")

    # 2️⃣ Update subscription in Stripe
    subscription = stripe.Subscription.modify(
        app.stripe_subscription_id,
        cancel_at_period_end=False,
        proration_behavior="create_prorations",
        items=[{
            "id": stripe.Subscription.retrieve(app.stripe_subscription_id)["items"]["data"][0].id,
            "price": new_price_id,
        }],
    )

    # 3️⃣ Update local DB (application record)
    app.badge_type = getattr(models.BadgeType, badge_type)
    app.stripe_price_id = new_price_id
    db.commit()
    db.refresh(app)

    return {"message": f"Subscription changed to {badge_type}", "subscription": subscription}