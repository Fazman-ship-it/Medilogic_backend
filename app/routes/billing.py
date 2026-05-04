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

    # ======================================================
    # ✅ STEP 1: VALIDATE EXISTING CUSTOMER PROPERLY
    # ======================================================
    if org.stripe_customer_id:
        try:
            customer = stripe.Customer.retrieve(org.stripe_customer_id)

            # 🔥 THIS IS THE FIX (you were missing this)
            if getattr(customer, "deleted", False):
                raise Exception("Customer deleted in Stripe")

            print(f"✅ Existing Stripe customer valid: {org.stripe_customer_id}")
            return org.stripe_customer_id

        except Exception as e:
            print("⚠️ Invalid Stripe customer → recreating:", repr(e))
            org.stripe_customer_id = None
            db.commit()

    # ======================================================
    # ✅ STEP 2: CREATE NEW CUSTOMER
    # ======================================================
    try:
        customer = stripe.Customer.create(
            email=getattr(org, "email", None),
            name=f"Medilogic Org {org.id}",
            metadata={"organization_id": str(org.id)}
        )

        org.stripe_customer_id = customer.id
        db.commit()

        print(f"🔥 New Stripe customer created: {customer.id}")

        return customer.id

    except Exception as e:
        print("🔥 CUSTOMER CREATION ERROR:", repr(e))
        raise HTTPException(500, "Failed to create Stripe customer")

# ======================================================
# 🔄 UPDATE SUBSCRIPTION PRICE
# ======================================================
def update_org_subscription(db: Session, org: models.Organization):

    subscription = db.query(models.Subscription).filter(
        models.Subscription.org_id == org.id
    ).first()

    bill = calculate_org_bill(db, org.id)

    # 🚫 No bill → do nothing
    if bill["total"] <= 0:
        return

    # ======================================================
    # 🔥 CASE 1: NO SUBSCRIPTION → CREATE ONE
    # ======================================================
    if not subscription:
        print("🔥 No subscription → creating one")

        customer_id = create_or_get_customer(db, org)

        # get payment method
        payment_methods = stripe.PaymentMethod.list(
            customer=customer_id,
            type="card"
        )

        if not payment_methods.data:
            print("⚠️ No payment method → cannot create subscription")
            return

        default_pm = payment_methods.data[0].id

        stripe.Customer.modify(
            customer_id,
            invoice_settings={"default_payment_method": default_pm}
        )

        stripe_sub = stripe.Subscription.create(
            customer=customer_id,
            items=[{
                "price": os.getenv("STRIPE_PRICE_ID"),
                "quantity": int(bill["total"])
            }],
            default_payment_method=default_pm,
        )

        db_subscription = models.Subscription(
            org_id=org.id,
            stripe_subscription_id=stripe_sub.id,
            status="incomplete"
        )

        db.add(db_subscription)
        db.commit()

        print("✅ Subscription CREATED automatically")
        return

    # ======================================================
    # 🔄 CASE 2: SUBSCRIPTION EXISTS → UPDATE
    # ======================================================
    try:
        stripe_sub = stripe.Subscription.retrieve(
            subscription.stripe_subscription_id
        )

        item_id = stripe_sub["items"]["data"][0]["id"]

        stripe.Subscription.modify(
            subscription.stripe_subscription_id,
            items=[{
                "id": item_id,
                "quantity": int(bill["total"])
            }],
            proration_behavior="create_prorations"
        )

        print("✅ Subscription UPDATED automatically")

    except Exception as e:
        print("🔥 Subscription update error:", repr(e))
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

    print(f"🧠 Org ID: {org.id}")
    print(f"🧠 Existing customer: {org.stripe_customer_id}")

    customer_id = create_or_get_customer(db, org)

    print(f"🧠 Using customer_id: {customer_id}")

    try:
        setup_intent = stripe.SetupIntent.create(
            customer=customer_id,
            payment_method_types=["card"]
        )

        return {"client_secret": setup_intent.client_secret}

    except Exception as e:
        print("🔥 SETUP INTENT ERROR:", repr(e))
        raise HTTPException(500, "Failed to create setup intent")

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

    try:
        customer = stripe.Customer.retrieve(customer_id)

        default_pm = customer.get("invoice_settings", {}).get("default_payment_method")

        if not default_pm:
            payment_methods = stripe.PaymentMethod.list(
                customer=customer_id,
                type="card"
            )

            if not payment_methods.data:
                raise HTTPException(400, "No payment method found")

            default_pm = payment_methods.data[0].id

            stripe.Customer.modify(
                customer_id,
                invoice_settings={"default_payment_method": default_pm}
            )

        price_id = os.getenv("STRIPE_PRICE_ID")

        if not price_id:
            raise HTTPException(500, "Stripe price ID not configured")

        stripe_sub = stripe.Subscription.create(
            customer=customer_id,
            items=[{
                "price": price_id,
                "quantity": int(bill["total"])
            }],
            default_payment_method=default_pm,
        )

        db_subscription = db.query(models.Subscription).filter(
            models.Subscription.org_id == org.id
        ).first()

        # ✅ SAFE timestamp handling
        period_end_ts = stripe_sub.get("current_period_end")

        period_end = (
            datetime.fromtimestamp(period_end_ts, tz=timezone.utc)
            if period_end_ts
            else None
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

    has_payment_method = False
    live_status = "none"

    if org and subscription:
        try:
            # 🔥 ALWAYS FETCH FROM STRIPE (REAL-TIME)
            stripe_sub = stripe.Subscription.retrieve(
                subscription.stripe_subscription_id
            )

            # 🔥 MAP STATUS (same logic as webhook)
            if stripe_sub.status in ["active", "trialing"]:
                live_status = "active"
            elif stripe_sub.status in ["past_due", "unpaid"]:
                live_status = "past_due"
            elif stripe_sub.status in ["incomplete", "incomplete_expired"]:
                live_status = "incomplete"
            else:
                live_status = "inactive"

        except Exception as e:
            print("⚠️ Stripe fetch failed:", e)
            live_status = subscription.status  # fallback

    # 🔥 Payment method check (unchanged)
    if org:
        try:
            customer_id = create_or_get_customer(db, org)

            payment_methods = stripe.PaymentMethod.list(
                customer=customer_id,
                type="card"
            )

            has_payment_method = len(payment_methods.data) > 0

        except Exception as e:
            print("⚠️ Payment method check failed:", e)

    return {
        "subscription_status": live_status,  # 🔥 USE LIVE STATUS
        "has_subscription": bool(subscription),
        "has_payment_method": has_payment_method,
        "next_billing_date": subscription.current_period_end if subscription else None
    }
    
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

    try:
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

        # ✅ SAFE timestamp handling
        period_end_ts = stripe_sub.get("current_period_end")

        subscription.current_period_end = (
            datetime.fromtimestamp(period_end_ts, tz=timezone.utc)
            if period_end_ts
            else None
        )

        db.commit()

        return {"message": "Subscription synced"}

    except Exception as e:
        print("🔥 Sync FULL ERROR:", repr(e))
        raise HTTPException(500, "Failed to sync subscription")
        
@router.post("/billing/portal")
def create_portal_session(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    org = db.query(models.Organization).filter(
        models.Organization.id == current_user.organization_id
    ).first()

    if not org:
        raise HTTPException(404, "Organisation not found")

    # ======================================================
    # 🔥 FIX: ALWAYS USE SAFE CUSTOMER FUNCTION
    # ======================================================
    customer_id = create_or_get_customer(db, org)

    try:
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url="https://www.medilogicglobal.co.uk/company-admin/billing"
        )

        return {"url": session.url}

    except Exception as e:
        print("🔥 Portal FULL ERROR:", repr(e))
        raise HTTPException(500, "Failed to create portal session")
        
        
@router.get("/billing/preview-change")
def preview_billing_change(
    add_drivers: int = 0,
    add_clients: int = 0,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    org = db.query(models.Organization).filter(
        models.Organization.id == current_user.organization_id
    ).first()

    if not org:
        raise HTTPException(404, "Organisation not found")

    subscription = db.query(models.Subscription).filter(
        models.Subscription.org_id == org.id
    ).first()

    if not subscription:
        raise HTTPException(404, "Subscription not found")

    current_bill = calculate_org_bill(db, org.id)
    current_total = current_bill["total"]

    DRIVER_PRICE = 150
    CLIENT_PRICE = 50

    # 🔥 NEW TOTAL (your logic)
    change_amount = (add_drivers * DRIVER_PRICE) + (add_clients * CLIENT_PRICE)
    new_total = current_total + change_amount

    try:
        # ======================================================
        # 🔥 STRIPE REAL CALCULATION
        # ======================================================
        stripe_sub = stripe.Subscription.retrieve(
            subscription.stripe_subscription_id
        )

        item_id = stripe_sub["items"]["data"][0]["id"]

        upcoming_invoice = stripe.Invoice.upcoming(
            customer=org.stripe_customer_id,
            subscription=subscription.stripe_subscription_id,
            subscription_items=[{
                "id": item_id,
                "quantity": int(new_total)
            }]
        )

        # Stripe returns amount in pence
        amount_due = upcoming_invoice["amount_due"] / 100

    except Exception as e:
        print("⚠️ Stripe preview failed:", e)
        amount_due = change_amount  # fallback

    return {
        "current_total": current_total,
        "new_total": new_total,
        "prorated_charge": change_amount,
        "stripe_estimated_charge": amount_due,
        "message": f"Estimated charge now: £{amount_due}, next monthly: £{new_total}"
    }