from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional, List
from app.database import get_db
from app.dependencies import get_current_user
from app import models
from app.schemas import SubscriptionPlan
import stripe
import os
router = APIRouter()
def calculate_org_bill(db: Session, org_id: UUID):

    driver_count = db.query(models.User).filter(
        models.User.organization_id == org_id,
        models.User.role == "driver",
        models.User.is_verified == True,
        models.User.deleted_at == None   # 🔥 IMPORTANT
    ).count()

    client_count = db.query(models.User).filter(
        models.User.organization_id == org_id,
        models.User.role == "client",
        models.User.is_verified == True,
        models.User.deleted_at == None   # 🔥 IMPORTANT
    ).count()

    total_amount = (driver_count * 150) + (client_count * 50)

    return {
        "drivers": driver_count,
        "clients": client_count,
        "total": total_amount
    }

import stripe
import os
from sqlalchemy.orm import Session
from app import models

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")


def create_or_get_customer(db: Session, org: models.Organization):

    # ✅ If already exists → return it
    if org.stripe_customer_id:
        return org.stripe_customer_id

    # ✅ Create Stripe customer
    customer = stripe.Customer.create(
        email=org.email if hasattr(org, "email") else None,
        name=f"Medilogic Org {org.id}",
        metadata={"organization_id": str(org.id)}
    )

    # ✅ SAVE to DB (VERY IMPORTANT)
    org.stripe_customer_id = customer.id
    db.commit()

    return customer.id

def update_org_subscription(db: Session, org: models.Organization):
    from app.routes.billing import calculate_org_bill

    if not org.stripe_subscription_id:
        print("⚠️ No subscription found")
        return

    bill = calculate_org_bill(db, org.id)

    try:
        subscription = stripe.Subscription.retrieve(org.stripe_subscription_id)

        # 🔥 Get existing item ID
        item_id = subscription["items"]["data"][0].id

        # 🔥 UPDATE subscription price dynamically
        stripe.Subscription.modify(
            org.stripe_subscription_id,
            items=[{
                "id": item_id,
                "price_data": {
                    "currency": "gbp",
                    "product_data": {"name": "Medilogic Subscription"},
                    "unit_amount": int(bill["total"] * 100),
                    "recurring": {"interval": "month"},
                }
            }],
            proration_behavior="create_prorations"  # 🔥 IMPORTANT
        )

        print(f"✅ Subscription updated → £{bill['total']}")

    except Exception as e:
        print("❌ Stripe update failed:", str(e))

@router.post("/billing/setup-intent")
def create_setup_intent(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # 🔹 Get org
    org = db.query(models.Organization).filter(
        models.Organization.id == current_user.organization_id
    ).first()

    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")

    # 🔹 Create/get Stripe customer
    customer_id = create_or_get_customer(db, org)

    # 🔥 Create SetupIntent (SAVE CARD ONLY)
    setup_intent = stripe.SetupIntent.create(
        customer=customer_id,
        payment_method_types=["card"]
    )

    return {
        "client_secret": setup_intent.client_secret
    }


@router.post("/subscribe")
def subscribe_org(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # 🔐 ONLY ADMIN
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins allowed")

    # 🏢 GET ORG
    org = db.query(models.Organization).filter(
        models.Organization.id == current_user.organization_id
    ).first()

    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")

    # 💰 BILL
    bill = calculate_org_bill(db, org.id)

    if bill["total"] <= 0:
        raise HTTPException(status_code=400, detail="No billable users found")

    # 👤 CUSTOMER
    customer_id = create_or_get_customer(db, org)

    # ======================================================
    # 🔥 NEW: CHECK IF CARD EXISTS
    # ======================================================
    payment_methods = stripe.PaymentMethod.list(
        customer=customer_id,
        type="card"
    )

    if not payment_methods.data:
        raise HTTPException(
            status_code=400,
            detail="No payment method found. Please add a card first."
        )

    try:
        # 💵 CREATE PRICE
        price = stripe.Price.create(
            unit_amount=int(bill["total"] * 100),
            currency="gbp",
            recurring={"interval": "month"},
            product_data={"name": "Medilogic Subscription"},
        )

        # 🔥 CREATE SUBSCRIPTION (AUTO CHARGE)
        subscription = stripe.Subscription.create(
            customer=customer_id,
            items=[{"price": price.id}],
            collection_method="charge_automatically",
            default_payment_method=payment_methods.data[0].id,  # 🔥 IMPORTANT
        )

        # 💾 SAVE
        org.stripe_customer_id = customer_id
        org.stripe_subscription_id = subscription.id
        org.subscription_status = subscription.status

        db.commit()

        return {
            "message": "Subscription activated successfully",
            "subscription_id": subscription.id,
            "amount": bill["total"],
            "status": subscription.status,
        }

    except Exception as e:
        print("❌ Subscription creation failed:", str(e))
        raise HTTPException(status_code=500, detail="Failed to create subscription")
        
@router.post("/billing/portal")
def create_billing_portal(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    org = db.query(models.Organization).filter(
        models.Organization.id == current_user.organization_id
    ).first()

    if not org or not org.stripe_customer_id:
        raise HTTPException(status_code=404, detail="Customer not found")

    try:
        session = stripe.billing_portal.Session.create(
            customer=org.stripe_customer_id,
            return_url="https://medilogicglobal.co.uk/dashboard"
        )

        return {
            "url": session.url
        }

    except Exception as e:
        print("❌ Billing portal error:", str(e))
        raise HTTPException(status_code=500, detail="Failed to open billing portal")

@router.get("/billing/summary")
def get_billing_summary(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    org = db.query(models.Organization).filter(
        models.Organization.id == current_user.organization_id
    ).first()

    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")

    bill = calculate_org_bill(db, org.id)

    return {
        "drivers": bill["drivers"],
        "clients": bill["clients"],
        "monthly_total": bill["total"],
        "subscription_status": org.subscription_status,
        "next_billing_date": org.subscription_current_period_end
    }