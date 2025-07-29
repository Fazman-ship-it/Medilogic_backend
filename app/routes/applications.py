from fastapi import APIRouter, Depends, HTTPException,Query
from sqlalchemy.orm import Session
from app import models, schemas
from app.database import get_db
from app.utilites.logging import log_activity
from app.utilites.user_onboarding import send_welcome_email
from app.models import PendingApplication
from app.schemas import PendingApplicationCreate, PendingApplicationOut
from app.routes.access import get_password_hash
from typing import List, Optional
from app.dependencies import require_role, get_current_user
from app.models import User

router = APIRouter()

@router.post("/apply", response_model=PendingApplicationOut)
def submit_application(
    application: PendingApplicationCreate,
    db: Session = Depends(get_db)
):
    # 🚫 Check if email already applied
    existing = db.query(PendingApplication).filter(PendingApplication.email == application.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="You have already applied")

    # ✅ Hash password before storing
    hashed_pw = get_password_hash(application.password)

    new_app = PendingApplication(
        full_name=application.full_name,
        email=application.email,
        password=hashed_pw,
        role=application.role,
        organization_name=application.organization_name,
        organization_type=application.organization_type,
        regulated_country=application.regulated_country,
        regulated_state=application.regulated_state,
        regulated_region=application.regulated_region,
        status="pending"
    )

    db.add(new_app)
    db.commit()
    db.refresh(new_app)

    return new_app


@router.get("/pending-applications", response_model=List[PendingApplicationOut])
def get_pending_applications(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("super_admin"))
):
    pending_apps = db.query(PendingApplication).order_by(PendingApplication.submitted_at.desc()).all()
    return pending_apps
