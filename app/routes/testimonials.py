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
        is_approved=False,
    )

    db.add(new_testimonial)
    db.commit()
    db.refresh(new_testimonial)

    if current_user:
        log_activity(
            db=db,
            user_id=current_user.id,
            action="submit_testimonial",
            details=f"{current_user.email} submitted a testimonial"
        )

    return new_testimonial


# ✅ Admin/Super Admin sees ALL testimonials (pending + approved)
@router.get("/", response_model=List[schemas.TestimonialOut])
def list_all_testimonials(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if current_user.role not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Not authorised")

    return (
        db.query(models.Testimonial)
        .order_by(models.Testimonial.created_at.desc())
        .all()
    )


# ✅ Public sees approved only
@router.get("/public", response_model=List[schemas.TestimonialOut])
def list_public_testimonials(db: Session = Depends(get_db)):
    return (
        db.query(models.Testimonial)
        .filter(models.Testimonial.is_approved == True)  # noqa: E712
        .order_by(models.Testimonial.created_at.desc())
        .all()
    )


# ✅ Admin approves
@router.patch("/{testimonial_id}/approve", response_model=schemas.TestimonialOut)
def approve_testimonial(
    testimonial_id: UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if current_user.role not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Not authorised")

    testimonial = db.query(models.Testimonial).filter(
        models.Testimonial.id == testimonial_id
    ).first()

    if not testimonial:
        raise HTTPException(status_code=404, detail="Testimonial not found")

    if testimonial.is_approved:
        return testimonial

    testimonial.is_approved = True
    db.commit()
    db.refresh(testimonial)

    log_activity(
        db=db,
        user_id=current_user.id,
        action="approve_testimonial",
        details=f"Approved testimonial {testimonial.id}"
    )

    return testimonial