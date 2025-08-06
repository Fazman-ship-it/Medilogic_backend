from fastapi import APIRouter, Depends, HTTPException, Query,status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date
from app import models, schemas
from app.dependencies import get_db
from app.dependencies import get_current_user
from app.dependencies import require_role
from app.models import ShiftAssignment, User
from uuid import UUID

router = APIRouter(
    prefix="/shifts",
    tags=["Shift Management"]
)

# 🚧 Admin assigns a shift to a driver
@router.post("/assign", response_model=schemas.ShiftOut)
def assign_shift(
    data: schemas.ShiftAssignRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role not in ["admin", "superadmin"]:
        raise HTTPException(status_code=403, detail="Only admins can assign shifts")

    # Ensure driver exists and belongs to the same org (unless superadmin)
    driver = db.query(models.User).filter(models.User.id == data.driver_id).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    if current_user.role != "superadmin" and driver.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="You can only assign shifts within your organization")

    shift = models.ShiftAssignment(
        driver_id=data.driver_id,
        shift_date=data.shift_date,
        start_time=data.start_time,
        end_time=data.end_time,
        note=data.note,
        organization_id=driver.organization_id
    )
    db.add(shift)
    db.commit()
    db.refresh(shift)
    return shift

# 👁️ View all shifts (admin or driver)
@router.get("/", response_model=List[schemas.ShiftOut])
def get_shifts(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    driver_id: Optional[UUID] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None)
):
    query = db.query(models.ShiftAssignment)

    # Superadmin sees all, others see within their org
    if current_user.role != "superadmin":
        query = query.filter(models.ShiftAssignment.organization_id == current_user.organization_id)

    # Driver can only view their own shifts
    if current_user.role == "driver":
        query = query.filter(models.ShiftAssignment.driver_id == current_user.id)

    # Admin can optionally filter by driver in their org
    if driver_id:
        if current_user.role != "superadmin" and current_user.role != "admin":
            raise HTTPException(status_code=403, detail="Only admins can filter by driver")
        query = query.filter(models.ShiftAssignment.driver_id == driver_id)

    # Date filtering
    if start_date:
        query = query.filter(models.ShiftAssignment.shift_date >= start_date)
    if end_date:
        query = query.filter(models.ShiftAssignment.shift_date <= end_date)

    return query.order_by(models.ShiftAssignment.shift_date.asc()).all()



@router.delete("/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_shift_assignment(
    assignment_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    # ✅ Only admin or superadmin can delete
    if current_user.role not in ["admin", "superadmin"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    assignment = db.query(ShiftAssignment).filter_by(id=assignment_id).first()

    if not assignment:
        raise HTTPException(status_code=404, detail="Shift assignment not found")

    # ✅ Multi-tenant check (admin can only delete in their org)
    if current_user.role != "superadmin":
        if assignment.organization_id != current_user.organization_id:
            raise HTTPException(status_code=403, detail="You are not allowed to delete this assignment")

    db.delete(assignment)
    db.commit()

    return  # 204 No Content