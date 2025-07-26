from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app import models, schemas, database
from app.dependencies import get_current_user

router = APIRouter(prefix="/testimonials", tags=["Testimonials"])

@router.post("/", response_model=schemas.TestimonialOut)
def submit_testimonial(
    testimonial: schemas.TestimonialCreate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    new_testimonial = models.Testimonial(
        name=testimonial.name,
        content=testimonial.content,
        user_id=current_user.id
    )
    db.add(new_testimonial)
    db.commit()
    db.refresh(new_testimonial)
    return new_testimonial