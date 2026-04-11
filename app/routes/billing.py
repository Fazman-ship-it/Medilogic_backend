from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from app.database import get_db
from app.dependencies import get_current_user
from app import models
import stripe
import os

router = APIRouter()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
price_id = os.getenv("STRIPE_PRICE_ID")


# ======================================================
# 💰 BILL CALCULATION
# ======================================================
def calculate_org_bill(db: Session, org_id: UUID):

    driver_count = db.query(models.User).filter(
        models.User.organization_id == org_id,
        models.User.role == "driver",
        models.User.is_verified == True,
        models.User.deleted_at == None
    ).count()

    client_count = db.query(models.User).filter(
        models.User.organization_id == org_id,
        models.User.role == "client",
        models.User.is_verified == True,
        models.User.deleted_at == None
    ).count()

    total_amount = (driver_count * 150) + (client_count * 50)

    return {
        "drivers": driver_count,
        "clients": client_count,
        "total": total_amount
    }


# ======================================================
# 👤 CUSTOMER
# ======================================================
def create_or_get_customer(db: Session, org: models.Organization):

    if org.stripe_customer_id:
        return org.stripe_customer_id

    customer = stripe.Customer.create(
        email=getattr(org, "email", None),
        name=f"Medilogic Org {org.id}",
        metadata={"organization_id": str(org.id)}
    )

    org.stripe_customer_id = customer.id
    db.commit()

    return customer.id


# ======================================================
# 🔄 UPDATE SUBSCRIPTION PRICE
# ======================================================
def update_org_subscription(db: Session, org: models.Organization):

    if not org.stripe_subscription_id:
        return

    bill = calculate_org_bill(db, org.id)

    try:
        subscription = stripe.Subscription.retrieve(org.stripe_subscription_id)

        item_id = subscription["items"]["data"][0].id

        stripe.Subscription.modify(
            org.stripe_subscription_id,
            items=[{
                "id": item_id,
                "quantity": bill["total"]  # 🔥 UPDATE QUANTITY ONLY
            }],
            proration_behavior="create_prorations"
        )

        print(f"✅ Subscription updated → £{bill['total']}")

    except Exception as e:
        print("❌ Stripe update failed:", str(e))


# ======================================================
# 💳 SETUP INTENT
# ======================================================
@router.post("/billing/setup-intent")
def create_setup_intent(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    org = db.query(models.Organization).filter(
        models.Organization.id == current_user.organization_id
    ).first()

    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")

    customer_id = create_or_get_customer(db, org)

    setup_intent = stripe.SetupIntent.create(
        customer=customer_id,
        payment_method_types=["card"]
    )

    return {"client_secret": setup_intent.client_secret}


# ======================================================
# 🚀 SUBSCRIBE
# ======================================================
@router.post("/subscribe")
def subscribe_org(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):

    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins allowed")

    org = db.query(models.Organization).filter(
        models.Organization.id == current_user.organization_id
    ).first()

    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")

    bill = calculate_org_bill(db, org.id)

    if bill["total"] <= 0:
        raise HTTPException(status_code=400, detail="No billable users found")

    customer_id = create_or_get_customer(db, org)

    payment_methods = stripe.PaymentMethod.list(
        customer=customer_id,
        type="card"
    )

    if not payment_methods.data:
        raise HTTPException(
            status_code=400,
            detail="No payment method found"
        )

    try:
        price_id = os.getenv("STRIPE_PRICE_ID")

        # 🔥 CREATE SUBSCRIPTION WITH QUANTITY
        stripe_sub = stripe.Subscription.create(
            customer=customer_id,
            items=[{
                "price": price_id,
                "quantity": bill["total"]  # 💥 KEY CHANGE
            }],
            default_payment_method=payment_methods.data[0].id,
        )

        from datetime import datetime, timezone

        initial_status = "incomplete"

        period_end = None
        if stripe_sub.get("current_period_end"):
            period_end = datetime.fromtimestamp(
                stripe_sub["current_period_end"],
                tz=timezone.utc
            )

        db_subscription = db.query(models.Subscription).filter(
            models.Subscription.org_id == org.id
        ).first()

        if db_subscription:
            db_subscription.stripe_subscription_id = stripe_sub.id
            db_subscription.status = initial_status
            db_subscription.current_period_end = period_end
        else:
            db_subscription = models.Subscription(
                org_id=org.id,
                stripe_subscription_id=stripe_sub.id,
                status=initial_status,
                current_period_end=period_end
            )
            db.add(db_subscription)

        db.commit()

        return {
            "message": "Subscription created (pending confirmation)",
            "subscription_id": stripe_sub.id,
            "amount": bill["total"],
            "status": initial_status,
        }

    except Exception as e:
        print("❌ Subscription failed:", str(e))
        raise HTTPException(status_code=500, detail="Failed to create subscription")

# ======================================================
# 📊 SUMMARY
# ======================================================
@router.get("/billing/summary")
def get_billing_summary(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    org = db.query(models.Organization).filter(
        models.Organization.id == current_user.organization_id
    ).first()

    subscription = db.query(models.Subscription).filter(
        models.Subscription.org_id == org.id
    ).first()

    bill = calculate_org_bill(db, org.id)

    return {
        "drivers": bill["drivers"],
        "clients": bill["clients"],
        "monthly_total": bill["total"],
        "subscription_status": subscription.status if subscription else "none",
        "next_billing_date": subscription.current_period_end if subscription else None
    }


# ======================================================
# 📡 STATUS
# ======================================================
@router.get("/billing/status")
def billing_status(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    org = db.query(models.Organization).filter(
        models.Organization.id == current_user.organization_id
    ).first()

    subscription = db.query(models.Subscription).filter(
        models.Subscription.org_id == org.id
    ).first()

    return {
        "subscription_status": subscription.status if subscription else "none",
        "has_subscription": bool(subscription),
        "next_billing_date": subscription.current_period_end if subscription else None
    }