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
from app.utilites.email_utilites import send_email
from app.utilites.logging import log_activity
from app.dependencies import require_role
from sqlalchemy import case


# Create router for driver endpoints
router = APIRouter(prefix="/Medilogic_drivers", tags=[" Medilogic_Drivers"])

@router.post("/basic", response_model=schemas.MedilogicDriverOut)
def submit_basic_driver(
    payload: schemas.MedilogicDriverBase,  # 🔑 use a schema with password fields
    db: Session = Depends(get_db),
):
    """
    ✅ Step 1: A new driver submits their basic info (before approval).
    - Checks for duplicate email
    - Ensures passwords match
    - Hashes password before saving
    - Marks driver as submitted (inactive + unverified until super_admin approves)
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

    # ✅ Ensure passwords match
    if payload.password != payload.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")

    # ✅ Hash password before saving
    hashed_pw = get_password_hash(payload.password)

    # ✅ Create driver record
    driver = models.Medilogic_Driver(
        name=payload.name,
        email=payload.email,
        country=payload.country,
        state=payload.state,
        hashed_password=hashed_pw,  # 🔑 store only hashed password
        status=models.MedilogicDriverStatus.submitted,
        is_active=False,   # not active until approved
        is_verified=False, # not verified until approved
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

@router.get("/", response_model=List[schemas.MedilogicDriverOut])
def list_medilogic_drivers(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role(["super_admin", "admin"])),  # restrict access
    country: Optional[str] = Query(None, description="Filter by driver country"),
    state: Optional[str] = Query(None, description="Filter by driver state"),
    preferred_role: Optional[str] = Query(None, description="Filter by preferred role"),
    min_experience: Optional[int] = Query(None, description="Minimum years of experience"),
    status: Optional[str] = Query(None, description="Driver status (pending, approved, rejected)"),
):
    """
    List/Search Medilogic Drivers.
    - Only Super Admin & Org Admin can access.
    - Super Admin: sees all Medilogic drivers.
    - Org Admin: can also view Medilogic driver applications.
    - Filters: country, state, preferred_role, experience_years, status.
    - Results auto-sorted by subscription_status (Blue > Green > None).
    """
    query = db.query(models.Medilogic_Driver)

    # Apply filters
    if country:
        query = query.filter(models.Medilogic_Driver.country.ilike(f"%{country}%"))
    if state:
        query = query.filter(models.Medilogic_Driver.state.ilike(f"%{state}%"))
    if preferred_role:
        query = query.filter(models.Medilogic_Driver.preferred_role == preferred_role)
    if min_experience:
        query = query.filter(models.Medilogic_Driver.experience_years >= min_experience)
    if status:
        query = query.filter(models.Medilogic_Driver.status == status)

    # Subscription priority ordering (Blue > Green > None)
    subscription_order = case(
        (models.Medilogic_Driver.subscription_status == "blue", 3),
        (models.Medilogic_Driver.subscription_status == "green", 2),
        else_=1,
    )
    query = query.order_by(subscription_order.desc())

    return query.all()


@router.get("/{medilogic_driver_id}", response_model=schemas.MedilogicDriverOut)
def get_driver(
    medilogic_driver_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role(["super_admin", "admin"]))  # ✅ Role protection
):
    """
    Retrieve a single Medilogic driver application.

    - Super Admin & Admin: can view all Medilogic drivers.
    """
    driver = db.query(models.Medilogic_Driver).filter(
        models.Medilogic_Driver.medilogic_driver_id == medilogic_driver_id
    ).first()

    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    return driver

# app/routes/medilogic_drivers.py

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import Optional
from app import models, schemas
from app.database import get_db
from app.schemas import SubscriptionPlan, BadgeType
from app.utilites.subscribe_email import send_subscription_email  # utility to send emails


# app/routes/medilogic_drivers.py
from fastapi import APIRouter, Depends, HTTPException, Form, File, UploadFile
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, date
from app.database import get_db
from app.dependencies import require_role
from app import models, schemas
import stripe
from app.utilites.driver_subscription_utilities import check_subscription_status

stripe.api_key = "YOUR_STRIPE_SECRET_KEY"  # replace with env variable in production

@router.put("/me", response_model=schemas.MedilogicDriverOut)
async def update_profile_and_subscribe(
    # Profile fields
    email: Optional[str] = Form(None),
    name: Optional[str] = Form(None),
    date_of_birth: Optional[date] = Form(None),
    phone_number: Optional[str] = Form(None),
    country: Optional[str] = Form(None),
    state: Optional[str] = Form(None),
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

    # Fetch the medilogic driver
    medilogic_driver = db.query(models.Medilogic_Driver).filter(
        models.Medilogic_Driver.user_id == current_user.id
    ).first()
    if not medilogic_driver:
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
        "state": state,
        "address": address,
        "zip_code": zip_code,
        "vehicle_type": vehicle_type,
        "preferred_role": preferred_role,
        "experience_years": experience_years
    }
    for field, value in update_data.items():
        if value is not None:
            setattr(medilogic_driver, field, value)

    # -------------------------
    # Handle subscription/payment
    # -------------------------
    if plan:
        price_map = {
            schemas.SubscriptionPlan.green: 1099,  # pence
            schemas.SubscriptionPlan.blue: 1599
        }
        if plan not in price_map:
            raise HTTPException(status_code=400, detail="Invalid subscription plan")
        amount = price_map[plan]

        # Create Stripe PaymentIntent
        intent = stripe.PaymentIntent.create(
            amount=amount,
            currency="gbp",
            metadata={
                "medilogic_driver_id": str(medilogic_driver.id),
                "plan": plan.value
            }
        )

        # Save payment record
        payment = models.Payment(
            medilogic_driver_id=medilogic_driver.id,
            amount=amount / 100,
            currency="GBP",
            provider="stripe",
            reference=intent.id,
            status="pending",
            created_at=datetime.utcnow()
        )
        db.add(payment)

    # -------------------------
    # Check subscription status before document upload
    # -------------------------
    medilogic_driver = check_subscription_status(medilogic_driver)

    # -------------------------
    # Restrict document uploads for free users
    # -------------------------
    if medilogic_driver.subscription_plan == schemas.SubscriptionPlan.free:
        if files:
            raise HTTPException(
                status_code=403,
                detail="You must subscribe to Green (£10.99) or Blue (£15.99) to upload documents"
            )

    # -------------------------
    # Handle document uploads
    # -------------------------
    if files and medilogic_driver.subscription_plan in [schemas.SubscriptionPlan.green, schemas.SubscriptionPlan.blue]:
        for file in files:
            doc = models.Document(
                medilogic_driver_id=medilogic_driver.id,
                filename=file.filename,
                file_path=f"/uploads/{file.filename}",  # adjust storage logic
                upload_time=datetime.utcnow(),
                doc_type=file.content_type
            )
            db.add(doc)

    # -------------------------
    # Badge-based access
    # -------------------------
    if medilogic_driver.badge_type == "blue":
        medilogic_driver.can_view_analytics = True
        medilogic_driver.can_see_org_names = True
    elif medilogic_driver.badge_type == "green":
        medilogic_driver.can_view_analytics = True  # Green gets basic analytics
        medilogic_driver.can_see_org_names = False
    else:  # free
        medilogic_driver.can_view_analytics = False
        medilogic_driver.can_see_org_names = False

    # -------------------------
    # Analytics path
    # -------------------------
    analytics = None
    if medilogic_driver.badge_type in ["green", "blue"]:
        analytics = {
            "profile_views": medilogic_driver.profile_views,
            "org_views": medilogic_driver.org_views,
            "charts": {}
        }
        if medilogic_driver.badge_type == "blue":
            # Blue gets detailed charts (e.g., time series)
            charts = db.query(
                models.Medilogic_DriverProfileView.viewed_at
            ).filter(
                models.Medilogic_DriverProfileView.medilogic_driver_id == medilogic_driver.id
            ).all()
            analytics["charts"]["views_over_time"] = charts

    db.commit()
    db.refresh(medilogic_driver)

    # -------------------------
    # Prepare response
    # -------------------------
    response = {"driver": medilogic_driver, "analytics": analytics}
    if plan:
        response["client_secret"] = intent.client_secret
        response["payment_id"] = str(payment.id)

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