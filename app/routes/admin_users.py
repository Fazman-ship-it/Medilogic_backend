from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app import models, schemas, database
from app.dependencies import require_role, get_current_user
from app.utilites.logging import log_activity
from app.models import User
from app.database import get_db
from uuid import UUID

router = APIRouter(prefix="/admin", tags=["Admin - Users"])

@router.get("/users", response_model=List[schemas.UserAdminOut])
def get_users_by_role(
    role: Optional[str] = Query(None, regex="^(client|driver)$"),
    is_active: Optional[bool] = Query(
        None,
        description="Filter by active/inactive. If not provided, returns both."
    ),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of records to return"),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    # ✅ Require admin role
    require_role("admin")(current_user)

    # ✅ Base query - only users within the same organization
    query = db.query(models.User).filter(
        models.User.organization_id == current_user.organization_id
    )

    # ✅ Filter by role (client or driver) if provided
    if role:
        query = query.filter(models.User.role == role)

    # ✅ Filter by active/inactive if provided, otherwise show both
    if is_active is not None:
        query = query.filter(models.User.is_active == is_active)

    # ✅ Order by newest first, then paginate
    users = (
        query.order_by(models.User.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    return users


@router.patch("/users/{user_id}/activate")
def activate_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(require_role("admin")),
):
    user = db.query(User).filter(
        User.id == user_id,
        User.organization_id == current_user.organization_id
    ).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_active = True
    db.commit()

    # ✅ Log activity
    log_activity(
        db=db,
        user_id=current_user.id,
        action="activate_user",
        details=f"{current_user.role} activated user {user.name} (org={user.organization_id})"
    )

    return {"message": f"User {user.name} activated"}


@router.patch("/users/{user_id}/deactivate")
def deactivate_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(require_role("admin")),
):
    user = db.query(User).filter(
        User.id == user_id,
        User.organization_id == current_user.organization_id
    ).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_active = False
    db.commit()

    # ✅ Log activity
    log_activity(
        db=db,
        user_id=current_user.id,
        action="deactivate_user",
        details=f"{current_user.role} deactivated user {user.name} (org={user.organization_id})"
    )

    return {"message": f"User {user.name} deactivated"}

