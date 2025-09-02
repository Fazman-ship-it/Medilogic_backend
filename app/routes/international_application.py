# app/routes/international_applications.py
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from uuid import UUID
from app.database import get_db
from app import models, schemas
from app.models import InternationalApplication, InternationalApplicationStatus, Payment 
from app.auth import get_password_hash, generate_temp_password
from app.utilites.logging import log_activity
from app.utilites.applicant_email import send_applicant_approved_email
from app.dependencies import get_current_user, require_role
import uuid, os, shutil
import datetime as dt
from datetime import datetime, timedelta
from app.utilites.email_utilites import send_email
from sqlalchemy import func

router = APIRouter(prefix="/applications/international", tags=["International Applications"])

UPLOAD_DIR = "static/applications"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/basic", response_model=schemas.IntlApplicationOut)
def submit_basic_application(
    payload: schemas.IntlBasicCreate,
    db: Session = Depends(get_db),
):
    # Prevent duplicate applications by email
    exists = db.query(InternationalApplication).filter(
        InternationalApplication.email == payload.email,
        InternationalApplication.status.in_([
            InternationalApplicationStatus.submitted,
            InternationalApplicationStatus.approved
        ])
    ).first()
    if exists:
        raise HTTPException(
            status_code=400,
            detail="Application already submitted or approved with this email"
        )

    # ✅ Ensure passwords match
    if payload.password != payload.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")

    # ✅ Hash password before saving
    hashed_pw = get_password_hash(payload.password)

    try:
        app = InternationalApplication(
            email=payload.email,
            name=payload.name,
            country=payload.country,
            state=payload.state,
            zip_code=payload.zip_code,
            hashed_password=hashed_pw,  # store hashed password only
            status=InternationalApplicationStatus.submitted,
        )
        db.add(app)
        db.commit()
        db.refresh(app)
        return app
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Error creating application")

@router.patch("/super/{application_id}/approve", response_model=schemas.IntlApplicationOut)
def approve_application(
    application_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("super_admin")),
):
    """
    ✅ Approve an international application:
    - Ensure not already approved
    - Create loginable user with role "applicant_international"
    - Link user to application
    - Commit safely with rollback on errors
    - Then send email & log activity
    """
    app = db.query(InternationalApplication).filter(
        InternationalApplication.id == application_id
    ).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    if app.status == InternationalApplicationStatus.approved:
        raise HTTPException(status_code=400, detail="Already approved")

    # --- DB Transaction ---
    try:
        # Generate temporary password
        temp_password = generate_temp_password()

        # Create user
        new_user = models.User(
            email=app.email,
            name=app.name,
            role="applicant_international",  # ✅ make sure this role exists
            hashed_password=get_password_hash(temp_password),
            is_verified=True
        )
        db.add(new_user)
        db.flush()  # assign id without committing

        # Update application
        app.status = InternationalApplicationStatus.approved
        app.user_id = new_user.id

        db.commit()
        db.refresh(app)

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Approval failed: {str(e)}")

    # --- Non-DB operations (safe after commit) ---
    try:
        send_applicant_approved_email(
            to_email=app.email,
            full_name=app.name,
            temp_password=temp_password,
            login_link="https://medilogic.vercel.app/login"
        )
    except Exception as e:
        # Log email failure, but don’t rollback DB
        log_activity(
            db=db,
            user_id=current_user.id,
            action="email_failed",
            details=f"Failed to send approval email to {app.email}: {str(e)}"
        )

    # Audit log for approval
    log_activity(
        db=db,
        user_id=current_user.id,
        action="approve_international_application",
        details=f"Approved international application {app.id} ({app.email})"
    )

    return app

@router.patch("/super/{application_id}/reject", response_model=schemas.IntlApplicationOut)
def reject_application(
    application_id: UUID,
    reason: str = "Not specified",
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("super_admin")),
):
    app = db.query(InternationalApplication).filter(InternationalApplication.id == application_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    if app.status == InternationalApplicationStatus.rejected:
        raise HTTPException(status_code=400, detail="Already rejected")

    app.status = InternationalApplicationStatus.rejected
    db.commit()
    db.refresh(app)

    log_activity(
        db=db,
        user_id=current_user.id,
        action="reject_international_application",
        details=f"Rejected international application {app.id} ({app.email}). Reason: {reason}"
    )

    return app

@router.patch("/me/details", response_model=schemas.IntlApplicationOut)
def update_details(
    payload: schemas.IntlDetailsUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # Must be the created/approved applicant
    app = db.query(InternationalApplication).filter(
        InternationalApplication.user_id == current_user.id
    ).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    # Update only non-gated fields
    for field, value in payload.dict(exclude_unset=True).items():
        setattr(app, field, value)

    db.commit()
    db.refresh(app)

    log_activity(
        db=db,
        user_id=current_user.id,
        action="update_international_application_details",
        details=f"Updated details for application {app.id}"
    )

    return app

from app.models import Payment
from app.dependencies import require_application_fee_paid
from app.config import settings
import stripe

# routes/payments.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import stripe
from app import models
from app.database import get_db
from app.dependencies import get_current_user
from app.config import settings
import uuid
from datetime import datetime

@router.post("/me/pay-application-fee")
def pay_application_fee(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # 1. Find user’s application
    app = db.query(models.InternationalApplication).filter(
        models.InternationalApplication.user_id == current_user.id
    ).first()

    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    if app.has_paid_application_fee:
        return {"message": "Application fee already paid"}

    # 2. Create a pending payment record in DB
    payment = models.Payment(
        id=uuid.uuid4(),
        application_id=app.id,
        medilogic_driver_id=None,  # not relevant for app fee
        amount=200.00,  # 💡 define in settings (e.g. settings.APPLICATION_FEE_AMOUNT)
        currency="GBP",
        provider="stripe",
        status="pending",
        created_at=datetime.utcnow(),
        is_verified=False,
        payment_type="application_fee"
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)

    # 3. Create Stripe Checkout Session
    checkout = stripe.checkout.Session.create(
        mode="payment",
        payment_method_types=["card"],
        customer_email=current_user.email,
        line_items=[{
            "price": settings.STRIPE_APPLICATION_FEE_PRICE_ID,  
            "quantity": 1,
        }],
        metadata={  # ✅ link Stripe session to DB payment
            "payment_id": str(payment.id),
            "application_id": str(app.id),
            "user_id": str(current_user.id)
        },
        success_url="https://your-frontend/success?session_id={CHECKOUT_SESSION_ID}",
        cancel_url="https://your-frontend/cancel",
    )

    return {"checkout_url": checkout.url}

# GATED uploads (requires payment)
def _save_upload(prefix: str, f: UploadFile):
    ext = os.path.splitext(f.filename)[1]
    new_name = f"{prefix}_{uuid.uuid4()}{ext}"
    path = os.path.join(UPLOAD_DIR, new_name)
    with open(path, "wb") as buf:
        shutil.copyfileobj(f.file, buf)
    return path

@router.post("/me/upload/cv", response_model=schemas.IntlApplicationOut)
def upload_cv(
    file: UploadFile = File(...),
    app = Depends(require_application_fee_paid),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    app.cv_path = _save_upload("cv", file)
    db.commit()
    db.refresh(app)
    log_activity(db=db, user_id=current_user.id, action="upload_cv", details=f"Uploaded CV for application {app.id}")
    return app

@router.post("/me/upload/passport", response_model=schemas.IntlApplicationOut)
def upload_passport(
    file: UploadFile = File(...),
    app = Depends(require_application_fee_paid),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    app.passport_path = _save_upload("passport", file)
    db.commit()
    db.refresh(app)
    log_activity(db=db, user_id=current_user.id, action="upload_passport", details=f"Uploaded passport for application {app.id}")
    return app

@router.post("/me/upload/drivers-license", response_model=schemas.IntlApplicationOut)
def upload_drivers_license(
    file: UploadFile = File(...),
    app = Depends(require_application_fee_paid),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    app.drivers_license_path = _save_upload("license", file)
    db.commit()
    db.refresh(app)
    log_activity(db=db, user_id=current_user.id, action="upload_drivers_license", details=f"Uploaded driver license for application {app.id}")
    return app

@router.post("/me/upload/personal_statement", response_model=schemas.IntlApplicationOut)
def upload_personal_statement_docs(
    file: UploadFile = File(...),
    app = Depends(require_application_fee_paid),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    app.personal_statement_path = _save_upload("personal_statement", file)
    db.commit()
    db.refresh(app)
    log_activity(db=db, user_id=current_user.id, action="upload_personal_statement_docs", details=f"Uploaded personal statement docs for application {app.id}")
    return app

@router.post("/me/upload/certificate", response_model=schemas.IntlApplicationOut)
def upload_certificate(
    file: UploadFile = File(...),
    app = Depends(require_application_fee_paid),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    app.certificate_path = _save_upload("certificate", file)
    db.commit()
    db.refresh(app)
    log_activity(db=db, user_id=current_user.id, action="upload_certificate", details=f"Uploaded certificate for application {app.id}")
    return app

from fastapi import Query

@router.get("/super", response_model=list[schemas.IntlApplicationOut])
def list_all_international_applications(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("super_admin")),
    country: str | None = Query(None, description="Filter by applicant's country"),
    status: str | None = Query(None, description="Filter by application status (e.g. pending, approved, rejected)"),
    search: str | None = Query(None, description="Search by applicant name or email"),
    sort_by: str = Query("created_at", description="Sort field (created_at, name, country)"),
    order: str = Query("desc", description="Sort order (asc, desc)"),
    skip: int = Query(0, ge=0, description="Pagination skip"),
    limit: int = Query(20, le=100, description="Pagination limit")
):
    query = db.query(InternationalApplication)

    # Filtering
    if country:
        query = query.filter(InternationalApplication.country.ilike(f"%{country}%"))
    if status:
        query = query.filter(InternationalApplication.status == status)
    if search:
        query = query.filter(
            (InternationalApplication.full_name.ilike(f"%{search}%")) |
            (InternationalApplication.email.ilike(f"%{search}%"))
        )

    # Sorting
    sort_column = getattr(InternationalApplication, sort_by, None)
    if sort_column is not None:
        if order.lower() == "desc":
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())
    else:
        query = query.order_by(InternationalApplication.created_at.desc())

    # Pagination
    apps = query.offset(skip).limit(limit).all()
    return apps

from fastapi import Query

@router.get("/admin/applications")
def list_paid_applications_for_org_admins(
    country: str = None,
    start_date: datetime = None,
    end_date: datetime = None,
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=100, description="Max records to return"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin"))
):
    query = db.query(models.InternationalApplication).filter(
        models.InternationalApplication.has_paid_application_fee == True,
        models.InternationalApplication.status == "submitted"
    )

    if country:
        query = query.filter(models.InternationalApplication.country == country)
    if start_date and end_date:
        query = query.filter(
            models.InternationalApplication.created_at.between(start_date, end_date)
        )

    total_count = query.count()

    # Order by badge priority (blue > green > none), then newest first
    apps = (
        query.order_by(
            db.case(
                (models.InternationalApplication.badge_type == models.BadgeType.blue, 1),
                (models.InternationalApplication.badge_type == models.BadgeType.green, 2),
                else_=3
            ),
            models.InternationalApplication.created_at.desc()
        )
        .offset(skip)
        .limit(limit)
        .all()
    )

    return {
        "total": total_count,
        "skip": skip,
        "limit": limit,
        "applications": apps
    }
    
@router.get("/admin/applications/{application_id}", response_model=schemas.IntlApplicationOut)
async def get_application_by_id(
    application_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin"))
):
    app = db.query(models.InternationalApplication).filter(
        models.InternationalApplication.id == application_id,
        models.InternationalApplication.has_paid_application_fee == True
    ).first()

    if not app:
        return {"error": "Application not found"}

    # ✅ Record a new view with badge awareness
    new_view = models.ApplicationView(
        application_id=app.id,
        organization_id=current_user.organization_id,
        badge_type=app.badge_type
    )
    db.add(new_view)
    db.commit()

    # ✅ Trigger email notification to applicant
    subject = "Your application has been viewed"
    body = f"""
    <p>Hello {app.full_name},</p>
    <p>Your international application was viewed today by <b>{current_user.organization.name}</b>.</p>
    <p>Keep checking your dashboard for updates.</p>
    <br>
    <p>- Medilogic Team</p>
    """
    await send_email(subject, [app.email], body)

    return app


@router.get("/dashboard")
def finance_dashboard(
    db: Session = Depends(get_db),
    user=Depends(require_role("super_admin"))
):
    # 1. Total international applicants
    total_applicants = db.query(InternationalApplication).count()

    # 2. Applicants who paid application fee
    paid_applicants = db.query(InternationalApplication).filter(
        InternationalApplication.has_paid_application_fee == True
    ).count()

    # Sum revenue from payments marked as application fees (amount ~ 150)
    one_term_revenue = db.query(func.sum(Payment.amount)).filter(
        Payment.is_verified == True,
        Payment.amount == 200
    ).scalar() or 0

    # 3. Subscriptions by badge
    green_subs = db.query(InternationalApplication).filter(
        InternationalApplication.badge_type == "green",
        InternationalApplication.subscription_status == "active"
    ).count()

    blue_subs = db.query(InternationalApplication).filter(
        InternationalApplication.badge_type == "blue",
        InternationalApplication.subscription_status == "active"
    ).count()

    # Revenue from subscriptions
    sub_revenue = db.query(func.sum(Payment.amount)).filter(
        Payment.is_verified == True,
        Payment.amount != 200
    ).scalar() or 0

    # 4. Monthly revenue trend (last 6 months)
    last_6_months = []
    for i in range(6):
        month_start = (datetime.utcnow().replace(day=1) - timedelta(days=30*i)).replace(day=1)
        month_end = (month_start + timedelta(days=32)).replace(day=1)  # next month 1st day

        month_revenue = db.query(func.sum(Payment.amount)).filter(
            Payment.is_verified == True,
            Payment.created_at >= month_start,
            Payment.created_at < month_end
        ).scalar() or 0

        last_6_months.append({
            "month": month_start.strftime("%b %Y"),
            "revenue": float(month_revenue)
        })

    return {
        "applicants": {
            "total": total_applicants,
            "paid_application_fee": paid_applicants,
            "one_term_revenue": float(one_term_revenue)
        },
        "subscriptions": {
            "green_active": green_subs,
            "blue_active": blue_subs,
            "revenue": float(sub_revenue)
        },
        "monthly_revenue_trend": list(reversed(last_6_months))
    }