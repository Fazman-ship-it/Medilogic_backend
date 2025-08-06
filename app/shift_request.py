from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app import models, schemas
from app.dependencies import get_db
from app.dependencies import get_current_user
from datetime import datetime
from typing import List, Optional
from app.schemas import ShiftRequestCreate, ShiftRequestOut, ShiftRequestUpdate

router = APIRouter(
    prefix="/shifts/requests",
    tags=["Shift Requests"]
)

# 🚚 Driver submits request
@router.post("/", response_model=schemas.ShiftRequestOut)
def request_shift(
    data: schemas.ShiftRequestCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role != "driver":
        raise HTTPException(status_code=403, detail="Only drivers can request shifts.")

    shift = db.query(models.Shift).filter_by(id=data.shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found.")

    # Check if already requested
    existing = db.query(models.ShiftRequest).filter_by(driver_id=current_user.id, shift_id=data.shift_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="You have already requested this shift.")

    shift_request = models.ShiftRequest(
        driver_id=current_user.id,
        shift_id=data.shift_id,
        organization_id=current_user.organization_id
    )
    db.add(shift_request)
    db.commit()
    db.refresh(shift_request)

    return shift_request

@router.get("/", response_model=List[schemas.ShiftRequestOut])
def get_requests(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Access denied.")

    query = db.query(models.ShiftRequest)
    if current_user.role == "admin":
        query = query.filter(models.ShiftRequest.organization_id == current_user.organization_id)

    return query.order_by(models.ShiftRequest.requested_at.desc()).all()


@router.patch("/{request_id}")
def update_shift_request(
    request_id: int,
    update: ShiftRequestUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Access denied.")

    shift_request = db.query(models.ShiftRequest).filter_by(id=request_id).first()
    if not shift_request:
        raise HTTPException(status_code=404, detail="Shift request not found.")
    shift_request.status = update.status
    db.commit()

    return {"message": f"Shift request {update.status}."}