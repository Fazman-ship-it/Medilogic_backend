from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from uuid import UUID
from datetime import date
from typing import List, Optional
from sqlalchemy import Enum as SqlEnum
from enum import Enum
from app.utilites.medilogic_driver_applicant import send_driver_welcome_email
from app import models, schemas
from app.database import get_db
from app.auth import get_password_hash, generate_temp_password
from app.utilites.logging import log_activity
from app.dependencies import require_role, get_db, get_current_user 
from sqlalchemy import case
import os
from app.utilites.time_utilities import now_utc

# Create router for driver endpoints
router = APIRouter(prefix="/Medilogic_drivers", tags=[" Medilogic_Drivers"])

@router.post("/basic", response_model=schemas.MedilogicDriverOut)
def submit_basic_driver(
    payload: schemas.MedilogicDriverBase,
    db: Session = Depends(get_db),
):
    """
    Step 1: Driver submits BASIC application info only.
    """

    # ✅ Check duplicate email
    exists = db.query(models.Medilogic_Driver).filter(
        models.Medilogic_Driver.email == payload.email,
        models.Medilogic_Driver.status.in_([
            models.MedilogicDriverStatus.submitted,
            models.MedilogicDriverStatus.approved
        ])
    ).first()
    if exists:
        raise HTTPException(
            status_code=400,
            detail="Driver already submitted or approved with this email"
        )

    # ✅ Create BASIC driver record ONLY
    driver = models.Medilogic_Driver(
        name=payload.name,
        email=payload.email,
        phone_number=payload.phone_number,
        zip_code=payload.zip_code,
        country=payload.country,
        state=payload.state,
        status=models.MedilogicDriverStatus.submitted,
        is_active=False,
        is_verified=False,
    )

    db.add(driver)
    db.commit()
    db.refresh(driver)
    return driver

@router.patch("/super/{medilogic_driver_id}/approve", response_model=schemas.MedilogicDriverOut)
def approve_driver(
    medilogic_driver_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("super_admin")),
):
    """
    ✅ Step 2: Super admin approves driver.
    - Creates User account with temp password
    - Marks driver as approved, active, verified
    - Sends welcome email with login link
    - Logs activity
    """
    driver = db.query(models.Medilogic_Driver).filter(
        models.Medilogic_Driver.id == medilogic_driver_id
    ).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    if driver.status == models.MedilogicDriverStatus.approved:
        raise HTTPException(status_code=400, detail="Already approved")

    # ✅ Generate temp password
    temp_password = generate_temp_password()

    # ✅ Create User account for driver
    new_user = models.User(
        email=driver.email,
        name=driver.name,
        role="driver",
        hashed_password=get_password_hash(temp_password),
        is_verified=True,
        is_active=True,
    )
    db.add(new_user)
    db.flush()  # flush so new_user.id is available

    # ✅ Update driver record
    driver.status = models.MedilogicDriverStatus.approved
    driver.is_active = True
    driver.is_verified = True
    driver.user_id = new_user.id

    db.commit()
    db.refresh(driver)

    # ✅ Send welcome email
    send_driver_welcome_email(
        to_email=driver.email,
        full_name=driver.name,
        temp_password=temp_password,
        login_link="https://medilogic.vercel.app/login"
    )

    # ✅ Log activity
    log_activity(
        db=db,
        user_id=current_user.id,
        action="approve_driver",
        details=f"Approved driver {driver.id} ({driver.email})"
    )

    return driver

@router.patch("/{medilogic_driver_id}/reject", response_model=schemas.MedilogicDriverOut)
def reject_driver(
    medilogic_driver_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("super_admin")),
):
    """
    Reject a Medilogic driver application.
    """
    driver = db.query(models.Medilogic_Driver).filter(
        models.Medilogic_Driver.id == medilogic_driver_id
    ).first()

    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    # ✅ Update status fields
    driver.status = models.MedilogicDriverStatus.rejected
    driver.is_active = False
    driver.is_verified = False

    db.commit()
    db.refresh(driver)

    return driver

from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import case, cast, String
from app.dependencies import get_db, get_current_user
from app import models, schemas


@router.get("/", response_model=List[schemas.MedilogicDriverOut])
def list_medilogic_drivers(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    country: Optional[str] = Query(None, description="Filter by driver country"),
    region: Optional[str] = Query(None, description="Filter by driver region"),
    preferred_role: Optional[str] = Query(None, description="Filter by preferred role"),
    min_experience: Optional[int] = Query(None, description="Minimum years of experience"),
    status: Optional[str] = Query(None, description="Driver status (pending, approved, rejected)"),
):
    # ✅ ROLE CHECK
    if current_user.role not in ["super_admin", "admin"]:
        raise HTTPException(status_code=403, detail="Not authorised to access this resource")

    query = db.query(models.Medilogic_Driver)

    if country:
        query = query.filter(models.Medilogic_Driver.country.ilike(f"%{country}%"))
    if region:
        query = query.filter(models.Medilogic_Driver.region.ilike(f"%{region}%"))
    if preferred_role:
        query = query.filter(models.Medilogic_Driver.preferred_role == preferred_role)
    if min_experience:
        query = query.filter(models.Medilogic_Driver.experience_years >= min_experience)
    if status:
        query = query.filter(models.Medilogic_Driver.status == status)

    # ✅ UPDATED (Option 2): cast ENUM -> string before comparing
    subscription_order = case(
        (cast(models.Medilogic_Driver.subscription_status, String) == "blue", 3),
        (cast(models.Medilogic_Driver.subscription_status, String) == "green", 2),
        else_=1,
    )

    query = query.order_by(subscription_order.desc())

    return query.all()



@router.get("/{medilogic_driver_id}", response_model=schemas.MedilogicDriverOut)
def get_driver(
    medilogic_driver_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Retrieve a single Medilogic driver application.
    - super_admin/admin: can view any driver.
    - medilogic_driver: can only view their own driver record.
    """

    # ✅ Allow only these roles
    if current_user.role not in ["super_admin", "admin", "medilogic_driver"]:
        raise HTTPException(status_code=403, detail="Not authorised to access this resource")

    driver = db.query(models.Medilogic_Driver).filter(
        models.Medilogic_Driver.id == medilogic_driver_id
    ).first()

    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    # ✅ If medilogic_driver, restrict to OWN record only
    if current_user.role == "medilogic_driver":
        if not driver.user_id or driver.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorised to access this driver record")

    return driver
    
from app.utilites.time_utilities import now_utc
from fastapi import APIRouter, Depends, HTTPException, Form, File, UploadFile
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, date
import os
import stripe
import uuid
from app.database import get_db
from app.dependencies import require_role,get_db, get_current_user 
from app import models, schemas
from app.schemas import SubscriptionPlan, SubscriptionStatus, BadgeType
from app.utilites.storage_utilites import upload_file_to_s3_async

@router.put("/me", response_model=schemas.MedilogicDriverOut)
async def update_profile_and_subscribe(
    # Profile fields
    email: Optional[str] = Form(None),
    name: Optional[str] = Form(None),
    date_of_birth: Optional[date] = Form(None),
    phone_number: Optional[str] = Form(None),
    country: Optional[str] = Form(None),
    region: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    zip_code: Optional[str] = Form(None),
    license_number: Optional[str] = Form(None),
    license_expiry: Optional[date] = Form(None),
    vehicle_type: Optional[str] = Form(None),
    preferred_role: Optional[str] = Form(None),
    experience_years: Optional[int] = Form(None),
    # Subscription
    plan: Optional[schemas.SubscriptionPlan] = Form(None),
    # Document uploads
    files: List[UploadFile] = File([]),
    db: Session = Depends(get_db),
    current_user=Depends(require_role(["medilogic_driver"]))
):
    """
    Full Medilogic Driver dashboard update:
    - Update profile
    - Upload documents (Green/Blue only)
    - Subscribe/pay for plan (Stripe)
    - Access analytics based on badge
    """

    # Fetch the Medilogic driver
    driver = db.query(models.Medilogic_Driver).filter(
        models.Medilogic_Driver.user_id == current_user.id
    ).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    # -------------------------
    # Update profile fields
    # -------------------------
    update_data = {
        "email": email,
        "name": name,
        "date_of_birth": date_of_birth,
        "license_number": license_number,
        "license_expiry": license_expiry,
        "phone_number": phone_number,
        "country": country,
        "region": region,
        "address": address,
        "zip_code": zip_code,
        "vehicle_type": vehicle_type,
        "preferred_role": preferred_role,
        "experience_years": experience_years
    }
    for field, value in update_data.items():
        if value is not None:
            setattr(driver, field, value)

    # -------------------------
    # Handle subscription/payment via Stripe
    # -------------------------
    client_secret = None
    payment_id = None

    if plan and plan != schemas.SubscriptionPlan.free:
        price_map = {
            schemas.SubscriptionPlan.green: 1099,
            schemas.SubscriptionPlan.blue: 1599
        }
        if plan not in price_map:
            raise HTTPException(status_code=400, detail="Invalid subscription plan")
        amount = price_map[plan]

        # Stripe Customer
        if not driver.stripe_customer_id:
            customer = stripe.Customer.create(
                email=driver.email,
                name=driver.name,
                metadata={"driver_id": str(driver.id)}
            )
            driver.stripe_customer_id = customer.id
        else:
            customer = stripe.Customer.retrieve(driver.stripe_customer_id)

        # Stripe Subscription
        price_id_map = {
            schemas.SubscriptionPlan.green: os.getenv("STRIPE_GREEN_PRICE_ID"),
            schemas.SubscriptionPlan.blue: os.getenv("STRIPE_BLUE_PRICE_ID")
        }
        subscription = stripe.Subscription.create(
            customer=customer.id,
            items=[{"price": price_id_map[plan]}],
            metadata={"driver_id": str(driver.id), "plan": plan.value},
            expand=["latest_invoice.payment_intent"]
        )

        # Save Payment record
        payment = models.Payment(
            medilogic_driver_id=driver.id,
            amount=amount / 100,
            currency="GBP",
            provider="stripe",
            reference=subscription.id,
            status="pending",
            payment_type="subscription",
            created_at=now_utc()
        )
        db.add(payment)

        # Update driver Stripe subscription info
        driver.stripe_subscription_id = subscription.id
        driver.stripe_price_id = price_id_map[plan]
        driver.cancel_at_period_end = False  # new subscription starts active
        client_secret = subscription.latest_invoice.payment_intent.client_secret
        payment_id = str(payment.id)

    # -------------------------
    # Restrict document uploads for free users
    # -------------------------
    if driver.subscription_plan == schemas.SubscriptionPlan.free and files:
        raise HTTPException(
            status_code=403,
            detail="You must subscribe to Green or Blue to upload documents"
        )

    # -------------------------
    # Handle document uploads (S3 production)
    # -------------------------
    if files and driver.subscription_plan in [schemas.SubscriptionPlan.green, schemas.SubscriptionPlan.blue]:
        for file in files:
        # ✅ Upload directly with async helper
            key = await upload_file_to_s3_async(file, prefix=f"drivers/{driver.id}")

        # ✅ Save metadata to DB
            doc = models.Document(
                medilogic_driver_id=driver.id,
                filename=file.filename,
                file_path=key,  # S3 key
                upload_time=now_utc(),
                doc_type=file.content_type
            )
            db.add(doc)

    # -------------------------
    # Badge-based access
    # -------------------------
    if driver.badge_type == BadgeType.blue.value:
        driver.can_view_analytics = True
        driver.can_see_org_names = True
    elif driver.badge_type == BadgeType.green.value:
        driver.can_view_analytics = True
        driver.can_see_org_names = False
    else:
        driver.can_view_analytics = False
        driver.can_see_org_names = False

    # -------------------------
    # Analytics path
    # -------------------------
    analytics = None
    if driver.badge_type in [BadgeType.green.value, BadgeType.blue.value]:
        analytics = {
            "profile_views": getattr(driver, "profile_views", 0),
            "org_views": getattr(driver, "org_views", 0),
            "charts": {}
        }
        if driver.badge_type == BadgeType.blue.value:
            charts = db.query(
                models.DriverView.viewed_at
            ).filter(
                models.DriverView.medilogic_driver_id == driver.id
            ).all()
            analytics["charts"]["views_over_time"] = charts

    db.commit()
    db.refresh(driver)

    # -------------------------
    # Prepare response
    # -------------------------
    response = {"driver": driver, "analytics": analytics}
    if client_secret:
        response["client_secret"] = client_secret
        response["payment_id"] = payment_id

    return response

@router.get("/driver", response_model=schemas.MedilogicDriverAnalyticsOut)
def get_medilogic_driver_analytics(
    db: Session = Depends(get_db),
    current_user=Depends(require_role(["medilogic_driver"]))
):
    """
    Return analytics data for the logged-in Medilogic driver.
    - Only Blue and Green badge drivers have access
    """
    medilogic_driver = db.query(models.Medilogic_Driver).filter(
        models.Medilogic_Driver.user_id == current_user.id
    ).first()

    if not medilogic_driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    if medilogic_driver.badge_type not in ["green", "blue"]:
        raise HTTPException(status_code=403, detail="Upgrade to Green or Blue to access analytics")

    # Example analytics
    profile_views = medilogic_driver.profile_views
    org_views = medilogic_driver.org_views  # {"org_name": count}

    # Blue badge gets extra charts / insights
    charts = {}
    if medilogic_driver.badge_type == "blue":
        # Generate a time series of profile views for Plotly/JS charting
        charts["views_over_time"] = db.query(
            models.DriverProfileView.viewed_at
        ).filter(
            models.DriverProfileView.medilogic_driver_id == medilogic_driver.id
        ).all()

    return {
        "profile_views": profile_views,
        "org_views": org_views,
        "charts": charts
    }
    
# app/routes/medilogic_drivers.py
from fastapi import APIRouter, HTTPException, Depends, Form
from sqlalchemy.orm import Session
from datetime import datetime
from app.database import get_db
from app.dependencies import require_role
from app import models, schemas
import stripe
import os
from app.utilites.time_utilities import now_utc
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

@router.put("/driver/subscription", response_model=schemas.MedilogicDriverOut)
def change_subscription(
    new_plan: schemas.SubscriptionPlan = Form(...),
    db: Session = Depends(get_db),
    current_user=Depends(require_role(["medilogic_driver"]))
):
    """
    Upgrade or downgrade a Medilogic Driver subscription.
    """
    driver = db.query(models.Medilogic_Driver).filter(
        models.Medilogic_Driver.user_id == current_user.id
    ).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    if new_plan == driver.subscription_plan:
        raise HTTPException(status_code=400, detail="You are already on this plan")

    # Ensure Stripe Customer exists
    if not driver.stripe_customer_id:
        customer = stripe.Customer.create(
            email=driver.email,
            name=driver.name,
            metadata={"driver_id": str(driver.id)}
        )
        driver.stripe_customer_id = customer.id
    else:
        customer = stripe.Customer.retrieve(driver.stripe_customer_id)

    # Map plan to Stripe price IDs
    price_id_map = {
        schemas.SubscriptionPlan.green: os.getenv("STRIPE_GREEN_PRICE_ID"),
        schemas.SubscriptionPlan.blue: os.getenv("STRIPE_BLUE_PRICE_ID")
    }

    if new_plan not in price_id_map:
        raise HTTPException(status_code=400, detail="Invalid plan")

    # Fetch current subscription
    if driver.stripe_subscription_id:
        stripe.Subscription.modify(
            driver.stripe_subscription_id,
            cancel_at_period_end=False,
            items=[{
                "id": stripe.Subscription.retrieve(driver.stripe_subscription_id).items.data[0].id,
                "price": price_id_map[new_plan]
            }]
        )
    else:
        # Create new subscription
        subscription = stripe.Subscription.create(
            customer=customer.id,
            items=[{"price": price_id_map[new_plan]}],
            metadata={"driver_id": str(driver.id), "plan": new_plan.value},
            expand=["latest_invoice.payment_intent"]
        )
        driver.stripe_subscription_id = subscription.id

    # Update driver plan and badge/features
    driver.subscription_plan = new_plan
    driver.subscription_status = schemas.SubscriptionStatus.active
    driver.subscription_start = now_utc()
    driver.subscription_end = None  # Stripe handles recurring
    if new_plan == schemas.SubscriptionPlan.green:
        driver.badge_type = schemas.BadgeType.green
        driver.can_upload_docs = True
        driver.can_view_analytics = True
        driver.can_see_org_names = False
    elif new_plan == schemas.SubscriptionPlan.blue:
        driver.badge_type = schemas.BadgeType.blue
        driver.can_upload_docs = True
        driver.can_view_analytics = True
        driver.can_see_org_names = True
    db.commit()
    db.refresh(driver)

    return driver 


@router.delete("/driver/subscription", response_model=schemas.MedilogicDriverOut)
def cancel_subscription(
    at_period_end: bool = True,
    db: Session = Depends(get_db),
    current_user=Depends(require_role(["medilogic_driver"]))
):
    """
    Cancel the Medilogic Driver's subscription.
    - at_period_end=True → cancel at the end of billing cycle
    - at_period_end=False → cancel immediately
    """
    driver = db.query(models.Medilogic_Driver).filter(
        models.Medilogic_Driver.user_id == current_user.id
    ).first()

    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    if not driver.stripe_subscription_id:
        raise HTTPException(status_code=400, detail="No active subscription to cancel")

    # Cancel Stripe subscription
    stripe.Subscription.modify(
        driver.stripe_subscription_id,
        cancel_at_period_end=at_period_end
    )

    # Update driver status/features
    if at_period_end:
        driver.subscription_status = schemas.SubscriptionStatus.cancelled
    else:
        driver.subscription_status = schemas.SubscriptionStatus.cancelled
        driver.subscription_plan = schemas.SubscriptionPlan.free
        driver.badge_type = schemas.BadgeType.none
        driver.can_upload_docs = False
        driver.can_view_analytics = False
        driver.can_see_org_names = False
        driver.subscription_end = now_utc()
        driver.stripe_subscription_id = None  # remove reference to Stripe subscription

    db.commit()
    db.refresh(driver)

    return driver   