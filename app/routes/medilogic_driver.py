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
from app.dependencies import get_current_user 
from sqlalchemy import case
import os
from app.utilites.time_utilities import now_utc
from app.database import get_db

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
        role="medilogic_driver",
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

# ✅ ADD THIS ENDPOINT (do not change your other endpoints)

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from app.dependencies import get_current_user
from app import models, schemas
from app.database import get_db

@router.get("/me", response_model=schemas.MedilogicDriverOut)
def get_my_medilogic_driver_profile(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    ✅ Medilogic driver fetches ONLY their own Medilogic driver record.
    """

    # ✅ Only medilogic_driver can use this endpoint
    if current_user.role != "medilogic_driver":
        raise HTTPException(status_code=403, detail="Not authorised to access this resource")

    # ✅ Find driver record linked to THIS user
    driver = db.query(models.Medilogic_Driver).filter(
        models.Medilogic_Driver.user_id == current_user.id
    ).first()

    if not driver:
        raise HTTPException(status_code=404, detail="Driver profile not found")

    return driver


from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import case, cast, String
from app.dependencies import get_current_user
from app import models, schemas
from app.database import get_db


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
from app.dependencies import get_current_user 
from app import models, schemas
from app.schemas import SubscriptionPlan, SubscriptionStatus, BadgeType
from app.utilites.storage_utilites import upload_file_to_s3_async

import logging
from uuid import uuid4
logger = logging.getLogger(__name__)

@router.put("/me", response_model=schemas.MedilogicDriverMeOut)
async def update_profile_and_subscribe(
    # Profile fields
    email: Optional[str] = Form(None),
    name: Optional[str] = Form(None),
    date_of_birth: Optional[date] = Form(None),
    phone_number: Optional[str] = Form(None),
    country: Optional[str] = Form(None),
    state: Optional[str] = Form(None),
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
    current_user: models.User = Depends(get_current_user),  # ✅ normal auth
):
    request_id = str(uuid4())[:8]

    def _safe(v):
        # Avoid dumping huge/sensitive values into logs
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            if len(s) > 80:
                return s[:80] + "…"
            return s
        return v

    logger.info(
        "[%s] PUT /me called user_id=%s role=%s has_files=%s plan=%s",
        request_id,
        getattr(current_user, "id", None),
        getattr(current_user, "role", None),
        any(f and getattr(f, "filename", "") for f in (files or [])),
        getattr(plan, "value", plan),
    )

    # ✅ ONLY Medilogic drivers allowed
    if current_user.role != "medilogic_driver":
        logger.warning(
            "[%s] Forbidden role=%s user_id=%s",
            request_id,
            getattr(current_user, "role", None),
            getattr(current_user, "id", None),
        )
        raise HTTPException(status_code=403, detail="Only Medilogic drivers can access this resource")

    # Fetch the Medilogic driver
    driver = db.query(models.Medilogic_Driver).filter(
        models.Medilogic_Driver.user_id == current_user.id
    ).first()
    if not driver:
        logger.warning("[%s] Driver not found for user_id=%s", request_id, current_user.id)
        raise HTTPException(status_code=404, detail="Driver not found")

    logger.info("[%s] Loaded driver id=%s user_id=%s", request_id, driver.id, driver.user_id)

    # -------------------------
    # Update profile fields
    # -------------------------
    update_data = {
        "email": email,
        "name": name,
        "date_of_birth": date_of_birth,
        "region": region,
        "license_number": license_number,
        "license_expiry": license_expiry,
        "phone_number": phone_number,
        "country": country,
        "state": state,
        "address": address,
        "zip_code": zip_code,
        "vehicle_type": vehicle_type,
        "preferred_role": preferred_role,
        "experience_years": experience_years
    }

    USER_EDITABLE_FIELDS = {"email", "name"}
    DRIVER_EDITABLE_FIELDS = {
        "phone_number",
        "zip_code",
        "address",
        "state",
        "region",
        "date_of_birth",
        "license_number",
        "license_expiry",
        "country",
        "preferred_role",
        "vehicle_type",
        "experience_years",
    }

    # Snapshot before
    before_user = {"email": getattr(current_user, "email", None), "name": getattr(current_user, "name", None)}
    before_driver = {k: getattr(driver, k, None) for k in DRIVER_EDITABLE_FIELDS.union(USER_EDITABLE_FIELDS)}

    incoming_keys = [k for k, v in update_data.items() if v is not None]
    logger.info("[%s] Incoming update keys=%s", request_id, incoming_keys)

    applied_user = {}
    applied_driver = {}
    skipped = {}

    for field, value in update_data.items():
        if value is None:
            continue
        if isinstance(value, str) and value.strip() == "":
            skipped[field] = "empty_string"
            continue

        if field in USER_EDITABLE_FIELDS:
            applied_user[field] = _safe(value)
            setattr(current_user, field, value)
            # keep driver in sync too (your model has these cols)
            applied_driver[field] = _safe(value)
            setattr(driver, field, value)
        elif field in DRIVER_EDITABLE_FIELDS:
            applied_driver[field] = _safe(value)
            setattr(driver, field, value)
        else:
            skipped[field] = "not_whitelisted"

    logger.info("[%s] Applied USER fields=%s", request_id, applied_user)
    logger.info("[%s] Applied DRIVER fields=%s", request_id, applied_driver)
    if skipped:
        logger.info("[%s] Skipped fields=%s", request_id, skipped)

    # -------------------------
    # Handle subscription/payment via Stripe
    # -------------------------
    client_secret = None
    payment_id = None

    if plan and plan != schemas.SubscriptionPlan.free:
        logger.info("[%s] Subscription requested plan=%s", request_id, getattr(plan, "value", plan))

        price_map = {
            schemas.SubscriptionPlan.green: 1099,
            schemas.SubscriptionPlan.blue: 1599
        }
        if plan not in price_map:
            logger.warning("[%s] Invalid subscription plan=%s", request_id, getattr(plan, "value", plan))
            raise HTTPException(status_code=400, detail="Invalid subscription plan")

        amount = price_map[plan]

        # Stripe Customer
        if not driver.stripe_customer_id:
            logger.info("[%s] Creating Stripe customer for driver_id=%s", request_id, driver.id)
            customer = stripe.Customer.create(
                email=driver.email,
                name=driver.name,
                metadata={"driver_id": str(driver.id)}
            )
            driver.stripe_customer_id = customer.id
        else:
            logger.info("[%s] Retrieving Stripe customer=%s", request_id, driver.stripe_customer_id)
            customer = stripe.Customer.retrieve(driver.stripe_customer_id)

        # Stripe Subscription
        price_id_map = {
            schemas.SubscriptionPlan.green: os.getenv("STRIPE_GREEN_PRICE_ID"),
            schemas.SubscriptionPlan.blue: os.getenv("STRIPE_BLUE_PRICE_ID")
        }

        if not price_id_map.get(plan):
            logger.error("[%s] Missing STRIPE price id in env for plan=%s", request_id, getattr(plan, "value", plan))
            raise HTTPException(status_code=500, detail="Stripe price ID not configured")

        logger.info("[%s] Creating Stripe subscription customer=%s plan=%s", request_id, customer.id, plan.value)
        subscription = stripe.Subscription.create(
            customer=customer.id,
            items=[{"price": price_id_map[plan]}],
            metadata={"driver_id": str(driver.id), "plan": plan.value},
            expand=["latest_invoice.payment_intent"]
        )

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

        driver.stripe_subscription_id = subscription.id
        driver.stripe_price_id = price_id_map[plan]
        driver.cancel_at_period_end = False
        client_secret = subscription.latest_invoice.payment_intent.client_secret
        payment_id = str(payment.id)

        driver.subscription_plan = plan
        driver.subscription_status = schemas.SubscriptionStatus.active
        driver.subscription_start = now_utc()
        driver.subscription_end = None

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

        logger.info("[%s] Subscription persisted in DB plan=%s badge=%s", request_id, driver.subscription_plan, driver.badge_type)

    # -------------------------
    # Restrict document uploads for free users
    # -------------------------
    has_real_files = any(f and getattr(f, "filename", "") for f in (files or []))
    logger.info("[%s] has_real_files=%s subscription_plan=%s", request_id, has_real_files, getattr(driver, "subscription_plan", None))

    if driver.subscription_plan == schemas.SubscriptionPlan.free and has_real_files:
        logger.warning("[%s] Upload blocked due to free plan driver_id=%s", request_id, driver.id)
        raise HTTPException(status_code=403, detail="You must subscribe to Green or Blue to upload documents")

    # -------------------------
    # Handle document uploads (S3 production)
    # -------------------------
    if has_real_files and driver.subscription_plan in [schemas.SubscriptionPlan.green, schemas.SubscriptionPlan.blue]:
        for file in files:
            if not getattr(file, "filename", ""):
                continue

            logger.info("[%s] Uploading file=%s driver_id=%s", request_id, file.filename, driver.id)
            key = await upload_file_to_s3_async(file, prefix=f"drivers/{driver.id}")

            doc = models.Document(
                medilogic_driver_id=driver.id,
                filename=file.filename,
                file_path=key,
                upload_time=now_utc(),
                doc_type=file.content_type
            )
            db.add(doc)
            logger.info("[%s] Document row staged filename=%s key=%s", request_id, file.filename, key)

    # -------------------------
    # Badge-based access
    # -------------------------
    prev_badge = getattr(driver, "badge_type", None)

    if driver.badge_type == BadgeType.blue.value:
        driver.can_view_analytics = True
        driver.can_see_org_names = True
    elif driver.badge_type == BadgeType.green.value:
        driver.can_view_analytics = True
        driver.can_see_org_names = False
    else:
        driver.can_view_analytics = False
        driver.can_see_org_names = False

    logger.info(
        "[%s] Badge access computed prev_badge=%s now_badge=%s can_view_analytics=%s can_see_org_names=%s",
        request_id,
        prev_badge,
        driver.badge_type,
        driver.can_view_analytics,
        driver.can_see_org_names,
    )

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

    # -------------------------
    # Commit + refresh
    # -------------------------
    try:
        db.commit()
        logger.info("[%s] DB commit OK driver_id=%s user_id=%s", request_id, driver.id, current_user.id)
    except Exception:
        logger.exception("[%s] DB commit FAILED driver_id=%s user_id=%s", request_id, driver.id, current_user.id)
        db.rollback()
        raise

    db.refresh(driver)
    db.refresh(current_user)

    # Snapshot after
    after_user = {"email": getattr(current_user, "email", None), "name": getattr(current_user, "name", None)}
    after_driver = {k: getattr(driver, k, None) for k in DRIVER_EDITABLE_FIELDS.union(USER_EDITABLE_FIELDS)}

    logger.info("[%s] BEFORE user=%s", request_id, {k: _safe(v) for k, v in before_user.items()})
    logger.info("[%s] AFTER  user=%s", request_id, {k: _safe(v) for k, v in after_user.items()})

    # Only log differences to keep logs clean
    diffs = {}
    for k in after_driver.keys():
        if before_driver.get(k) != after_driver.get(k):
            diffs[k] = {"before": _safe(before_driver.get(k)), "after": _safe(after_driver.get(k))}
    logger.info("[%s] DRIVER diffs=%s", request_id, diffs)

    # -------------------------
    # Prepare response
    # -------------------------
    response = {"driver": driver, "analytics": analytics}
    if client_secret:
        response["client_secret"] = client_secret
        response["payment_id"] = payment_id

    logger.info("[%s] Returning response client_secret=%s payment_id=%s", request_id, bool(client_secret), payment_id)

    return response
    
    
@router.get("/driver", response_model=schemas.MedilogicDriverAnalyticsOut)
def get_medilogic_driver_analytics(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),  # ✅ normal auth
):
    """
    Return analytics data for the logged-in Medilogic driver.
    - Only Blue and Green badge drivers have access
    """

    # ✅ ONLY Medilogic drivers allowed
    if current_user.role != "medilogic_driver":
        raise HTTPException(status_code=403, detail="Only Medilogic drivers can access analytics")

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
from app.dependencies import get_current_user
from app import models, schemas
import stripe
import os
from app.utilites.time_utilities import now_utc
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

@router.put("/driver/subscription", response_model=schemas.MedilogicDriverOut)
def change_subscription(
    new_plan: schemas.SubscriptionPlan = Form(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),  # ✅ normal auth
):
    """
    Upgrade or downgrade a Medilogic Driver subscription.
    """

    # ✅ Only Medilogic drivers allowed
    if current_user.role != "medilogic_driver":
        raise HTTPException(status_code=403, detail="Only Medilogic drivers can access this resource")

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
    current_user: models.User = Depends(get_current_user),  # ✅ normal auth
):
    """
    Cancel the Medilogic Driver's subscription.
    - at_period_end=True → cancel at the end of billing cycle
    - at_period_end=False → cancel immediately
    """

    # ✅ Only Medilogic drivers allowed
    if current_user.role != "medilogic_driver":
        raise HTTPException(status_code=403, detail="Only Medilogic drivers can access this resource")

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
        driver.stripe_subscription_id = None

    db.commit()
    db.refresh(driver)

    return driver