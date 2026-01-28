from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.dependencies import get_current_user, get_current_user_optional
from app.models import User
from app.utilites.logging import log_activity

router = APIRouter(prefix="/testimonials", tags=["Testimonials"])


# ✅ 1) Anyone can submit a testimonial (logged-in or not)
@router.post("/", response_model=schemas.TestimonialOut)
def submit_testimonial(
    testimonial: schemas.TestimonialCreate,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    new_testimonial = models.Testimonial(
        name=testimonial.name,
        content=testimonial.content,
        user_id=current_user.id if current_user else None,
        is_approved=False,  # ✅ default: admin approves later
    )

    db.add(new_testimonial)
    db.commit()
    db.refresh(new_testimonial)

    # ✅ Log only if user is authenticated
    if current_user:
        log_activity(
            db=db,
            user_id=current_user.id,
            action="submit_testimonial",
            details=f"{current_user.email} submitted a testimonial"
        )

    return new_testimonial


# ✅ 2) Public testimonials endpoint (approved only)
@router.get("/public", response_model=List[schemas.TestimonialOut])
def list_public_testimonials(
    db: Session = Depends(get_db),
):
    testimonials = (
        db.query(models.Testimonial)
        .filter(models.Testimonial.is_approved == True)  # noqa: E712
        .order_by(models.Testimonial.created_at.desc())
        .all()
    )
    return testimonials


# ✅ 3) Admin approves a testimonial
@router.patch("/{testimonial_id}/approve", response_model=schemas.TestimonialOut)
def approve_testimonial(
    testimonial_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # ✅ Only admin/super_admin can approve
    if current_user.role not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Not authorised")

    testimonial = db.query(models.Testimonial).filter(
        models.Testimonial.id == testimonial_id
    ).first()

    if not testimonial:
        raise HTTPException(status_code=404, detail="Testimonial not found")

    if testimonial.is_approved:
        return testimonial  # already approved, just return it

    testimonial.is_approved = True
    db.commit()
    db.refresh(testimonial)

    # ✅ Log admin action
    log_activity(
        db=db,
        user_id=current_user.id,
        action="approve_testimonial",
        details=f"Approved testimonial {testimonial.id}"
    )

    return testimonial