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

    # ✅ Define pricing clearly
    DRIVER_PRICE = 150
    CLIENT_PRICE = 50

    total_amount = (driver_count * DRIVER_PRICE) + (client_count * CLIENT_PRICE)

    return {
        "drivers": driver_count,
        "clients": client_count,
        "driver_price": DRIVER_PRICE,
        "client_price": CLIENT_PRICE,
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

    # ✅ Get subscription from DB (NEW CORRECT SOURCE)
    subscription = db.query(models.Subscription).filter(
        models.Subscription.org_id == org.id
    ).first()

    if not subscription:
        print("⚠️ No subscription found for org")
        return

    # ✅ Calculate latest bill
    bill = calculate_org_bill(db, org.id)

    try:
        # ✅ Get Stripe subscription
        stripe_sub = stripe.Subscription.retrieve(
            subscription.stripe_subscription_id
        )

        # ✅ Extract item ID safely
        item_id = stripe_sub["items"]["data"][0]["id"]

        # ✅ Update quantity (your current model)
        stripe.Subscription.modify(
            subscription.stripe_subscription_id,
            items=[{
                "id": item_id,
                "quantity": int(bill["total"])  # ✅ MUST be int
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

    # ✅ Calculate usage
    bill = calculate_org_bill(db, org.id)

    if bill["total"] <= 0:
        raise HTTPException(status_code=400, detail="No billable users found")

    customer_id = create_or_get_customer(db, org)

    try:
        # ============================================
        # ✅ STEP 1: GET CUSTOMER DEFAULT PAYMENT METHOD
        # ============================================
        customer = stripe.Customer.retrieve(customer_id)

        default_pm = customer.get("invoice_settings", {}).get("default_payment_method")

        # ============================================
        # ✅ STEP 2: IF NONE → SET ONE
        # ============================================
        if not default_pm:
            payment_methods = stripe.PaymentMethod.list(
                customer=customer_id,
                type="card"
            )

            if not payment_methods.data:
                raise HTTPException(
                    status_code=400,
                    detail="No payment method found"
                )

            default_pm = payment_methods.data[0].id

            # 🔥 CRITICAL FIX → SET DEFAULT PAYMENT METHOD
            stripe.Customer.modify(
                customer_id,
                invoice_settings={"default_payment_method": default_pm}
            )

        # ============================================
        # ✅ STEP 3: CREATE SUBSCRIPTION
        # ============================================
        price_id = os.getenv("STRIPE_PRICE_ID")

        if not price_id:
            raise HTTPException(500, "Stripe price ID not configured")

        stripe_sub = stripe.Subscription.create(
            customer=customer_id,
            items=[{
                "price": price_id,
                "quantity": int(bill["total"])  # keeping your current model
            }],
            default_payment_method=default_pm,
        )

        # ============================================
        # ✅ STEP 4: SAVE TO DB (ALWAYS INCOMPLETE)
        # ============================================
        db_subscription = db.query(models.Subscription).filter(
            models.Subscription.org_id == org.id
        ).first()

        period_end = datetime.fromtimestamp(
            stripe_sub.current_period_end,
            tz=timezone.utc
        )

        if db_subscription:
            db_subscription.stripe_subscription_id = stripe_sub.id
            db_subscription.status = "incomplete"
            db_subscription.current_period_end = period_end
        else:
            db_subscription = models.Subscription(
                org_id=org.id,
                stripe_subscription_id=stripe_sub.id,
                status="incomplete",
                current_period_end=period_end
            )
            db.add(db_subscription)

        db.commit()

        return {
            "message": "Subscription created (awaiting activation)",
            "subscription_id": stripe_sub.id,
        }

    except Exception as e:
        # 🔥 CRITICAL DEBUG FIX (DO NOT REMOVE)
        print("🔥 STRIPE FULL ERROR:", repr(e))

        raise HTTPException(
            status_code=500,
            detail=f"Stripe error: {str(e)}"
        )
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
    
@router.post("/billing/cancel")
def cancel_subscription(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    subscription = db.query(models.Subscription).filter(
        models.Subscription.org_id == current_user.organization_id
    ).first()

    if not subscription:
        raise HTTPException(404, "Subscription not found")

    stripe.Subscription.modify(
        subscription.stripe_subscription_id,
        cancel_at_period_end=True
    )

    return {"message": "Subscription will cancel at period end"}
    
@router.post("/billing/sync")
def sync_subscription(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    subscription = db.query(models.Subscription).filter(
        models.Subscription.org_id == current_user.organization_id
    ).first()

    if not subscription:
        raise HTTPException(404, "Subscription not found")

    stripe_sub = stripe.Subscription.retrieve(
        subscription.stripe_subscription_id
    )

    def map_status(s):
        if s in ["active", "trialing"]:
            return "active"
        elif s in ["past_due", "unpaid"]:
            return "past_due"
        elif s == "canceled":
            return "cancelled"
        return "inactive"

    subscription.status = map_status(stripe_sub.status)
    subscription.current_period_end = datetime.fromtimestamp(
        stripe_sub.current_period_end,
        tz=timezone.utc
    )

    db.commit()

    return {"message": "Subscription synced"}
    
    