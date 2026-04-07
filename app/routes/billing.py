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

def create_subscription(customer_id, amount):
    price = stripe.Price.create(
        unit_amount=amount * 100,
        currency="gbp",
        recurring={"interval": "month"},
        product_data={"name": "Medilogic Subscription"},
    )

    subscription = stripe.Subscription.create(
        customer=customer_id,
        items=[{"price": price.id}],
    )

    return subscription

router = APIRouter()
@router.post("/subscribe")
def subscribe_org(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # ======================================================
    # 🔐 ONLY ADMIN CAN SUBSCRIBE
    # ======================================================
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins allowed")

    # ======================================================
    # 🏢 GET ORGANIZATION
    # ======================================================
    org = db.query(models.Organization).filter(
        models.Organization.id == current_user.organization_id
    ).first()

    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")

    # ======================================================
    # 💰 CALCULATE BILL
    # ======================================================
    bill = calculate_org_bill(db, org.id)

    if bill["total"] <= 0:
        raise HTTPException(status_code=400, detail="No billable users found")

    # ======================================================
    # 👤 CREATE / GET STRIPE CUSTOMER
    # ======================================================
    customer_id = create_or_get_customer(db, org)

    try:
        # ======================================================
        # 💵 CREATE STRIPE PRICE (dynamic billing)
        # ======================================================
        price = stripe.Price.create(
            unit_amount=int(bill["total"] * 100),  # pence
            currency="gbp",
            recurring={"interval": "month"},
            product_data={"name": "Medilogic Subscription"},
        )

        # ======================================================
        # 🔥 CREATE SUBSCRIPTION (IMPORTANT FIX)
        # ======================================================
        subscription = stripe.Subscription.create(
            customer=customer_id,
            items=[{"price": price.id}],
            payment_behavior="default_incomplete",  # 🔥 REQUIRED
            expand=["latest_invoice.payment_intent"],  # 🔥 REQUIRED
        )

        # ======================================================
        # 💾 SAVE TO DB
        # ======================================================
        org.stripe_customer_id = customer_id
        org.stripe_subscription_id = subscription.id
        org.subscription_status = subscription.status

        db.commit()

        # ======================================================
        # 🔥 RETURN CLIENT SECRET FOR FRONTEND PAYMENT
        # ======================================================
        return {
            "message": "Subscription created. Complete payment.",
            "subscription_id": subscription.id,
            "client_secret": subscription.latest_invoice.payment_intent.client_secret,
            "amount": bill["total"],
            "status": subscription.status,
        }

    except Exception as e:
        print("❌ Subscription creation failed:", str(e))
        raise HTTPException(status_code=500, detail="Failed to create subscription")