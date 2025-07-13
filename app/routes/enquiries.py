from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app import schemas, models
from app.database import get_db
from app.dependencies import get_current_user
from app.dependencies import require_role
from typing import List
from app.utilites.logging import log_activity  # Ensure this utility exists
from typing import Optional
from app.dependencies import get_current_user_optional
from app.models import User
router = APIRouter(
    prefix="/enquiries",
    tags=["Enquiries"]
)

from fastapi import Request
from app.utilites.email_utilites import send_email  # Ensure this exists

@router.post("/", response_model=schemas.EnquiryOut)
def submit_enquiry(
    enquiry: schemas.EnquiryCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    ip_address = request.client.host
    user_agent = request.headers.get("user-agent", "Unknown")

    new_enquiry = models.Enquiry(
        name=enquiry.name,
        email=enquiry.email,
        message=enquiry.message,
        ip_address=ip_address,
        user_agent=user_agent,
        user_id=current_user.id if current_user else None,
        organization_id=current_user.organization_id if current_user else None
    )

    db.add(new_enquiry)
    db.commit()
    db.refresh(new_enquiry)

    # 📨 Notify support via email
    subject = f"New Enquiry from {enquiry.name}"
    body = f"""
    You received a new enquiry from Medilogic:

    • Name: {enquiry.name}
    • Email: {enquiry.email}
    • Message:
    {enquiry.message}

    • IP: {ip_address}
    • User Agent: {user_agent}
    """
    send_email(
        to_email="medilogicnotify@gmail.com",
        subject=subject,
        body=body
    )

    # 📋 Log the activity if submitted by a user
    if current_user:
        log_activity(
            db=db,
            user_id=current_user.id,
            action="submit_enquiry",
            details=f"{current_user.email} submitted an enquiry"
        )

    return new_enquiry

# 🔐 Super Admin Only: View all enquiries
@router.get("/", response_model=List[schemas.EnquiryOut])
def get_all_enquiries(
    db: Session = Depends(get_db),
    current_user=Depends(require_role("super_admin"))
):
    return db.query(models.Enquiry).order_by(models.Enquiry.created_at.desc()).all()