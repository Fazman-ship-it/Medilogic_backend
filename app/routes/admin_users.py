from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app import models, schemas, database
from app.dependencies import require_role, get_current_user

router = APIRouter(prefix="/admin", tags=["Admin - Users"])

@router.get("/users", response_model=List[schemas.UserAdminOut])
def get_users_by_role(
    role: Optional[str] = Query(None, regex="^(client|driver)$"),
    is_active: Optional[bool] = None,
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of records to return"),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    # ✅ Require admin role
    require_role("admin")(current_user)

    query = db.query(models.User).filter(models.User.organization_id == current_user.organization_id)

    # Filter by role if provided
    if role:
        query = query.filter(models.User.role == role)

    # Filter by active/inactive if provided
    if is_active is not None:
        query = query.filter(models.User.is_active == is_active)

    users = query.order_by(models.User.created_at.desc()).offset(skip).limit(limit).all()
    return users