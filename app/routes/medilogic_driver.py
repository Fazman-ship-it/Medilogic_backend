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
from app.dependencies import get_current_user, require_role
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
from app.dependencies import get_current_user, require_role
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
from app.dependencies import get_current_user,require_role
from app import models, schemas
from app.database import get_db

from sqlalchemy import case, cast, String, or_
from math import ceil

@router.get("/", response_model=schemas.MedilogicDriverListResponse)
def list_medilogic_drivers(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),

    # 🔍 Global search
    search: Optional[str] = Query(None),

    # Filters (ignored if search exists)
    country: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    preferred_role: Optional[str] = Query(None),
    min_experience: Optional[int] = Query(None),
    status: Optional[str] = Query(None),

    # 📄 Pagination
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
):

    # ✅ ROLE CHECK
    if current_user.role not in ["super_admin", "admin"]:
        raise HTTPException(status_code=403, detail="Not authorised")

    query = db.query(models.Medilogic_Driver)

    # =====================================================
    # 🔥 GLOBAL SEARCH (OVERRIDES FILTERS)
    # =====================================================
    if search:
        query = query.filter(
            or_(
                models.Medilogic_Driver.name.ilike(f"%{search}%"),
                models.Medilogic_Driver.email.ilike(f"%{search}%"),
                models.Medilogic_Driver.country.ilike(f"%{search}%"),
                models.Medilogic_Driver.region.ilike(f"%{search}%"),
            )
        )

    else:
        # -------------------------------------------------
        # NORMAL FILTERS
        # -------------------------------------------------

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

    # =====================================================
    # 🏆 SUBSCRIPTION PRIORITY (Blue → Green → Free)
    # =====================================================
    subscription_order = case(
        (cast(models.Medilogic_Driver.subscription_plan, String) == "blue", 3),
        (cast(models.Medilogic_Driver.subscription_plan, String) == "green", 2),
        (cast(models.Medilogic_Driver.subscription_plan, String) == "free", 1),
        else_=0,
    )

    query = query.order_by(
        subscription_order.desc(),
        models.Medilogic_Driver.created_at.desc()
    )

    # =====================================================
    # 📊 PAGINATION LOGIC
    # =====================================================
    total = query.count()

    offset = (page - 1) * page_size

    results = query.offset(offset).limit(page_size).all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "results": results,
    }
    
    
@router.get("/driver", response_model=schemas.MedilogicDriverAnalyticsOut)
def get_medilogic_driver_analytics(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
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

    # ==========================================================
    # DRIVER PROFILE VIEWS (FIXED)
    # ==========================================================
    profile_views = db.query(models.DriverView).filter(
        models.DriverView.medilogic_driver_id == medilogic_driver.id
    ).count()

    # ==========================================================
    # ORGANISATION VIEWS (Placeholder for now)
    # ==========================================================
    org_views = {}

    # ==========================================================
    # BLUE BADGE EXTRA ANALYTICS
    # ==========================================================
    charts = {}

    if medilogic_driver.badge_type == "blue":

        views_over_time = db.query(models.DriverView).filter(
            models.DriverView.medilogic_driver_id == medilogic_driver.id
        ).all()

        charts["views_over_time"] = [
            view.viewed_at for view in views_over_time
        ]

    return {
        "profile_views": profile_views,
        "org_views": org_views,
        "charts": charts
    }

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
from app.dependencies import get_current_user,require_role 
from app import models, schemas
from app.schemas import SubscriptionPlan, SubscriptionStatus, BadgeType
from app.utilites.storage_utilites import upload_file_to_s3_async

import logging
from uuid import uuid4
from typing import Optional, List
from datetime import date
from fastapi import Depends, HTTPException, Form
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from fastapi import Body

@router.put("/profile/json", response_model=schemas.MedilogicDriverOut)
def update_medilogic_driver_profile_json(
    payload: schemas.MedilogicDriverProfileUpdate = Body(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    request_id = str(uuid4())[:8]

    if current_user.role != "medilogic_driver":
        logger.warning("[%s] Forbidden role=%s user_id=%s", request_id, current_user.role, current_user.id)
        raise HTTPException(status_code=403, detail="Only Medilogic drivers can access this resource")

    driver = db.query(models.Medilogic_Driver).filter(
        models.Medilogic_Driver.user_id == current_user.id
    ).first()

    if not driver:
        logger.warning("[%s] Driver not found for user_id=%s", request_id, current_user.id)
        raise HTTPException(status_code=404, detail="Driver not found")

    update_data = payload.model_dump(exclude_unset=True)

    USER_FIELDS = {"email", "name"}
    applied = {"user": [], "driver": [], "skipped": []}

    for field, value in update_data.items():
        if value is None:
            continue
        if isinstance(value, str) and value.strip() == "":
            applied["skipped"].append(field)
            continue

        if field in USER_FIELDS:
            setattr(current_user, field, value)
            setattr(driver, field, value)
            applied["user"].append(field)
            applied["driver"].append(field)
        else:
            setattr(driver, field, value)
            applied["driver"].append(field)

    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("[%s] Commit failed user_id=%s driver_id=%s", request_id, current_user.id, driver.id)
        raise

    db.refresh(driver)
    db.refresh(current_user)

    logger.info("[%s] Profile updated(JSON) applied=%s", request_id, applied)
    return driver

import logging
from uuid import uuid4
logger = logging.getLogger(__name__)
from typing import List, Optional
from fastapi import UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import uuid4
from app import models, schemas
from app.database import get_db
from app.dependencies import get_current_user
from app.utilites.time_utilities import now_utc
from app.utilites.storage_utilites import upload_file_to_s3_async
from app.utilites.storage_utilites import generate_presigned_url_async
from app.models import BadgeType  # adjust import if needed

from app.utilites.storage_utilites import generate_presigned_url

@router.put("/me", response_model=schemas.MedilogicDriverMeOut)
async def update_me_upload_docs(
    files: List[UploadFile] = File([]),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    request_id = str(uuid4())[:8]

    # --------------------------------------------------
    # AUTH CHECK
    # --------------------------------------------------
    if current_user.role != "medilogic_driver":
        raise HTTPException(status_code=403, detail="Only Medilogic drivers can access this resource")

    driver = db.query(models.Medilogic_Driver).filter(
        models.Medilogic_Driver.user_id == current_user.id
    ).first()

    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    # --------------------------------------------------
    # UPLOAD LOGIC
    # --------------------------------------------------
    has_real_files = any(f and getattr(f, "filename", "") for f in (files or []))

    if driver.subscription_plan == schemas.SubscriptionPlan.free and has_real_files:
        raise HTTPException(status_code=403, detail="You must subscribe to Green or Blue")

    if has_real_files and driver.subscription_plan in [
        schemas.SubscriptionPlan.green,
        schemas.SubscriptionPlan.blue,
    ]:
        for file in files:
            if not getattr(file, "filename", ""):
                continue

            key = await upload_file_to_s3_async(file, prefix=f"drivers/{driver.id}")

            print("📤 UPLOADED FILE KEY:", key)

            doc = models.Document(
                medilogic_driver_id=driver.id,
                filename=file.filename,
                file_path=key,
                upload_time=now_utc(),
                doc_type=file.content_type,
            )

            db.add(doc)

    # --------------------------------------------------
    # BADGE LOGIC
    # --------------------------------------------------
    if driver.badge_type == BadgeType.blue.value:
        driver.can_view_analytics = True
        driver.can_see_org_names = True
    elif driver.badge_type == BadgeType.green.value:
        driver.can_view_analytics = True
        driver.can_see_org_names = False
    else:
        driver.can_view_analytics = False
        driver.can_see_org_names = False

    # --------------------------------------------------
    # ANALYTICS
    # --------------------------------------------------
    analytics = None
    if driver.badge_type in [BadgeType.green.value, BadgeType.blue.value]:
        analytics = {
            "profile_views": getattr(driver, "profile_views", 0),
            "org_views": getattr(driver, "org_views", 0),
            "charts": {},
        }

        if driver.badge_type == BadgeType.blue.value:
            charts = db.query(models.DriverView.viewed_at).filter(
                models.DriverView.medilogic_driver_id == driver.id
            ).all()

            analytics["charts"]["views_over_time"] = charts

    # --------------------------------------------------
    # SAVE TO DB
    # --------------------------------------------------
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        print("❌ DB COMMIT ERROR:", str(e))
        raise

    db.refresh(driver)

    # --------------------------------------------------
    # DEBUG
    # --------------------------------------------------
    print("🔍 TOTAL DOCUMENTS:", len(driver.documents))
    # --------------------------------------------------
    # BUILD DOCUMENTS WITH URL
    # --------------------------------------------------
    documents_with_urls = []

    for doc in driver.documents:
        print("🔍 FILE PATH:", doc.file_path)

        try:
            file_url = await generate_presigned_url(doc.file_path)
            print("✅ GENERATED URL:", file_url)
        except Exception as e:
            print("❌ URL GENERATION ERROR:", str(e))
            file_url = None

        documents_with_urls.append({
            "id": str(doc.id),
            "filename": doc.filename,
            "file_path": doc.file_path,
            "upload_time": doc.upload_time,
            "doc_type": doc.doc_type,
            "file_url": file_url,
        })

    # --------------------------------------------------
    # ✅ BUILD DRIVER DICT (CRITICAL FIX)
    # --------------------------------------------------
    driver_dict = {
        "id": str(driver.id),
        "name": driver.name,
        "email": driver.email,
        "subscription_plan": driver.subscription_plan,
        "badge_type": driver.badge_type,
        "documents": documents_with_urls,  # ✅ REAL DATA
        "can_upload_docs": driver.can_upload_docs,
        "can_view_analytics": driver.can_view_analytics,
        "can_see_org_names": driver.can_see_org_names,
    }

    # --------------------------------------------------
    # FINAL RETURN
    # --------------------------------------------------
    return {
        "driver": driver_dict,
        "analytics": analytics
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
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Form
from sqlalchemy.orm import Session
import os
import stripe

from app import models, schemas
from app.database import get_db
from app.dependencies import get_current_user
from app.utilites.time_utilities import now_utc

# If you use BadgeType like in /me
from app.models import BadgeType  # adjust import if your BadgeType lives elsewhere

@router.post("/driver/setup-intent")
def create_setup_intent(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if current_user.role != "medilogic_driver":
        raise HTTPException(status_code=403, detail="Only Medilogic drivers allowed")

    driver = db.query(models.Medilogic_Driver).filter(
        models.Medilogic_Driver.user_id == current_user.id
    ).first()

    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    # Ensure Stripe customer exists
    if not driver.stripe_customer_id:
        customer = stripe.Customer.create(
            email=driver.email,
            name=driver.name,
            metadata={"driver_id": str(driver.id)},
        )
        driver.stripe_customer_id = customer.id
        db.commit()
    else:
        customer = stripe.Customer.retrieve(driver.stripe_customer_id)

    setup_intent = stripe.SetupIntent.create(
        customer=customer.id,
        payment_method_types=["card"],
    )

    return {
        "client_secret": setup_intent.client_secret
    }
    
@router.put("/driver/subscription", response_model=schemas.MedilogicDriverSubscriptionChangeOut)
def change_subscription(
    new_plan: schemas.SubscriptionPlan = Form(...),
    payment_method_id: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):

    if current_user.role != "medilogic_driver":
        raise HTTPException(status_code=403, detail="Only Medilogic drivers can access this resource")

    driver = db.query(models.Medilogic_Driver).filter(
        models.Medilogic_Driver.user_id == current_user.id
    ).first()

    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    # ---------------------------------------------------
    # 🚨 FREE PLAN HANDLING
    # ---------------------------------------------------
    if new_plan == schemas.SubscriptionPlan.free:

        if driver.stripe_subscription_id:

            stripe.Subscription.modify(
                driver.stripe_subscription_id,
                cancel_at_period_end=True
            )

            driver.cancel_at_period_end = True
            driver.subscription_status = schemas.SubscriptionStatus.active
            driver.subscription_plan = schemas.SubscriptionPlan.free

            db.commit()
            db.refresh(driver)

        return {"driver": driver}

    # ---------------------------------------------------
    # STRIPE PRICE MAP
    # ---------------------------------------------------
    price_id_map = {
        schemas.SubscriptionPlan.green: os.getenv("STRIPE_GREEN_PRICE_ID"),
        schemas.SubscriptionPlan.blue: os.getenv("STRIPE_BLUE_PRICE_ID"),
    }

    price_id = price_id_map.get(new_plan)

    if not price_id:
        raise HTTPException(status_code=500, detail="Stripe price ID not configured")

    try:

        # ---------------------------------------------------
        # 1️⃣ Ensure Stripe customer exists
        # ---------------------------------------------------
        if not driver.stripe_customer_id:

            customer = stripe.Customer.create(
                email=driver.email,
                name=driver.name,
                metadata={"driver_id": str(driver.id)},
            )

            driver.stripe_customer_id = customer.id

        else:
            customer = stripe.Customer.retrieve(driver.stripe_customer_id)

        subscription = None

        # ===================================================
        # MODIFY EXISTING SUBSCRIPTION
        # ===================================================
        if driver.stripe_subscription_id:

            existing_subscription = stripe.Subscription.retrieve(
                driver.stripe_subscription_id
            )

            item_id = existing_subscription["items"]["data"][0]["id"]

            subscription = stripe.Subscription.modify(
                driver.stripe_subscription_id,
                items=[{
                    "id": item_id,
                    "price": price_id
                }],
                proration_behavior="create_prorations",
                cancel_at_period_end=False
            )

        # ===================================================
        # CREATE NEW SUBSCRIPTION
        # ===================================================
        else:

            if not payment_method_id:
                raise HTTPException(
                    status_code=400,
                    detail="payment_method_id is required for first subscription"
                )

            stripe.PaymentMethod.attach(
                payment_method_id,
                customer=customer.id,
            )

            stripe.Customer.modify(
                customer.id,
                invoice_settings={
                    "default_payment_method": payment_method_id
                }
            )

            subscription = stripe.Subscription.create(
                customer=customer.id,
                items=[{"price": price_id}],
                metadata={
                    "driver_id": str(driver.id),"plan": new_plan.value,
                },
                collection_method="charge_automatically",
                idempotency_key=f"subscription-create-{driver.id}"
            )

        # ---------------------------------------------------
        # Retrieve full subscription object
        # ---------------------------------------------------
        subscription = stripe.Subscription.retrieve(subscription.id)

        # ---------------------------------------------------
        # Update Local Database (NO BILLING DATES HERE)
        # ---------------------------------------------------
        driver.stripe_subscription_id = subscription.id
        driver.stripe_price_id = price_id
        driver.cancel_at_period_end = False

        # subscription status
        if subscription.status == "active":
            driver.subscription_status = schemas.SubscriptionStatus.active
            driver.subscription_plan = new_plan

        elif subscription.status in ["incomplete", "past_due"]:
            driver.subscription_status = schemas.SubscriptionStatus.past_due
            driver.subscription_plan = new_plan

        else:
            driver.subscription_status = schemas.SubscriptionStatus.none
            driver.subscription_plan = schemas.SubscriptionPlan.free

        db.commit()
        db.refresh(driver)

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Subscription update failed: {str(e)}"
        )

    return {
        "driver": driver,
    }
    
from app.routes.hookstripe import apply_plan_features    
@router.delete("/driver/subscription", response_model=schemas.MedilogicDriverOut)
def cancel_subscription(
    at_period_end: bool = True,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):

    if current_user.role != "medilogic_driver":
        raise HTTPException(status_code=403, detail="Only Medilogic drivers can access this resource")

    driver = db.query(models.Medilogic_Driver).filter(
        models.Medilogic_Driver.user_id == current_user.id
    ).first()

    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    if not driver.stripe_subscription_id:
        raise HTTPException(status_code=400, detail="No active subscription to cancel")

    try:
        stripe.Subscription.modify(
            driver.stripe_subscription_id,
            cancel_at_period_end=at_period_end
        )

        if at_period_end:
            # ✅ Still active but cancelling
            driver.subscription_status = schemas.SubscriptionStatus.active
            driver.cancel_at_period_end = True

        else:
            # ✅ Immediate cancellation
            driver.subscription_status = schemas.SubscriptionStatus.cancelled
            driver.cancel_at_period_end = False

            apply_plan_features(driver, schemas.SubscriptionPlan.free)

            driver.subscription_end = now_utc()

        db.commit()
        db.refresh(driver)

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Cancellation failed: {str(e)}")

    return driver                