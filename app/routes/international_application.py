# app/routes/international_applications.py
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from uuid import UUID
from app.database import get_db
from app import models, schemas
from app.models import InternationalApplication, InternationalApplicationStatus 
from app.auth import get_password_hash, generate_temp_password
from app.utilites.logging import log_activity
from app.utilites.applicant_email import send_applicant_approved_email
from app.dependencies import get_current_user, require_role
import uuid, os, shutil
import datetime as dt
from datetime import datetime

router = APIRouter(prefix="/applications/international", tags=["International Applications"])

UPLOAD_DIR = "static/applications"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/basic", response_model=schemas.IntlApplicationOut)
def submit_basic_application(
    payload: schemas.IntlBasicCreate,
    db: Session = Depends(get_db),
):
    # Prevent duplicate basic applications by email in submitted/approved states
    exists = db.query(InternationalApplication).filter(
        InternationalApplication.email == payload.email,
        InternationalApplication.status.in_([InternationalApplicationStatus.submitted, InternationalApplicationStatus.approved])
    ).first()
    if exists:
        raise HTTPException(status_code=400, detail="Application already submitted or approved with this email")

    app = InternationalApplication(
        email=payload.email,
        name=payload.name,
        country=payload.country,
        state=payload.state,
        zip_code=payload.zip_code,
        password=payload.password,
        confirm_password=payload.password,
        status=InternationalApplicationStatus.submitted,
    )
    db.add(app)
    db.commit()
    db.refresh(app)
    return app


@router.patch("/super/{application_id}/approve", response_model=schemas.IntlApplicationOut)
def approve_application(
    application_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("super_admin")),
):
    app = db.query(InternationalApplication).filter(InternationalApplication.id == application_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    if app.status == InternationalApplicationStatus.approved:
        raise HTTPException(status_code=400, detail="Already approved")

    # Create loginable user with role "applicant"
    temp_password = generate_temp_password()
    new_user = models.User(
        email=app.email,
        name=app.name,
        role="applicant_international",
        hashed_password=get_password_hash(temp_password),
        is_verified=True
    )
    db.add(new_user)
    db.flush()  # get id without full commit

    app.status = InternationalApplicationStatus.approved
    app.user_id = new_user.id
    db.commit()
    db.refresh(app)

    # Email the applicant
    send_applicant_approved_email(
        to_email=app.email,
        full_name=app.name,
        temp_password=temp_password,
        login_link="https://medilogic.vercel.app/login"
    )

    # Log
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

@router.post("/me/pay-application-fee")
def pay_application_fee(
    payload: schemas.PaymentCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    app = db.query(InternationalApplication).filter(
        InternationalApplication.user_id == current_user.id
    ).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    if app.has_paid_application_fee:
        return {"message": "Application fee already paid"}

    # Record payment (stub). Integrate Stripe/Paystack later or handle via webhook.
    payment = Payment(
        application_id=app.id,
        amount=150.00,
        currency="GBP",
        provider=payload.provider or "manual",
        reference=payload.reference or str(uuid.uuid4()),
        status="succeeded",
    )
    db.add(payment)

    app.has_paid_application_fee = True
    db.commit()

    log_activity(
        db=db,
        user_id=current_user.id,
        action="pay_application_fee",
        details=f"Paid application fee for application {app.id}"
    )

    return {"message": "Payment recorded. Gated uploads unlocked."}

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

@router.get("/admin/applications", response_model=list[schemas.IntlApplicationOut])
def list_paid_applications_for_org_admins(
    country: str = None,
    start_date: datetime = None,
    end_date: datetime = None,
    skip: int = Query(0, ge=0, description="Number of records to skip"),   # Pagination start
    limit: int = Query(20, ge=1, le=100, description="Max records to return"),  # Page size
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin"))
):
    query = db.query(InternationalApplication).filter(
        InternationalApplication.has_paid_application_fee == True,
        InternationalApplication.status == "submitted"
    )

    if country:
        query = query.filter(InternationalApplication.country == country)
    if start_date and end_date:
        query = query.filter(
            InternationalApplication.created_at.between(start_date, end_date)
        )

    total_count = query.count()  # total applications (for UI)

    apps = (
        query.order_by(InternationalApplication.created_at.desc())
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