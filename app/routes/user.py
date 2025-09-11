# app/routes/user.py
from app.schemas import UserCreate, UserOut
from app.models import User
from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from app import models
from ..database import get_db
from datetime import datetime
from pydantic import BaseModel, EmailStr
from fastapi.security import OAuth2PasswordBearer   
from sqlalchemy.orm import Session
from jose import JWTError, jwt
from app.database import get_db
from app.schemas import UserCreate, UserOut
from app.models import User
from datetime import datetime
from app import database
from app.dependencies import get_current_user,get_db  
from app.dependencies import require_role
from app.utilites.logging import log_activity
from app.schemas import UserUpdate
from app.models import Organization
from app.schemas import UserStatusOut
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime
from app.schemas import DeletedUser
from app.models import User, ActivityLog
from app.dependencies import get_db, get_current_user
from app.schemas import UserUpdate, DeleteAccountRequest
from app.utilites.logging import log_activity

router = APIRouter(prefix="/users", tags=['users'])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

@router.delete("/users/me", status_code=204)
def delete_own_account(
    request: DeleteAccountRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # ✅ Verify password
    if not pwd_context.verify(request.password, current_user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid password")

    # 🚫 Prevent double deletion
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Account already deleted")

    # 📝 Mark account as deleted instead of removing it
    current_user.is_active = False
    current_user.deleted_at = datetime.utcnow()
    current_user.deletion_reason = request.reason

    # 📝 Log activity (multi-tenant safe)
    log_activity(
        db=db,
        user_id=current_user.id,
        action="soft_delete_account",
        details=f"User {current_user.email} marked their account as deleted. Reason: {request.reason}"
    )

    db.commit()


@router.put("/update")
def update_my_account(
    updates: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Email uniqueness check
    if updates.email and updates.email != current_user.email:
        existing_user = db.query(User).filter_by(email=updates.email).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="Email already in use.")

    if updates.name:
        current_user.name = updates.name
    if updates.email:
        current_user.email = updates.email

    db.commit()
    db.refresh(current_user)

    log_activity(
        db=db,
        user_id=current_user.id,
        action="update_account",
        details=f"User updated their account. New name: {current_user.name}, New email: {current_user.email}"
    )

    return {
        "message": "Account updated successfully.",
        "user": {
            "name": current_user.name,
            "email": current_user.email
        }
    }
    
@router.patch("/users/{user_id}/restore", status_code=200)
def restore_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 🔎 Fetch user
    user_to_restore = db.query(User).filter(User.id == user_id).first()
    if not user_to_restore:
        raise HTTPException(status_code=404, detail="User not found")

    # 🔒 Access Control
    if current_user.role == "admin":
        if user_to_restore.organization_id != current_user.organization_id:
            raise HTTPException(status_code=403, detail="Admins can only restore users in their own organization")
    elif current_user.role != "super_admin":
        raise HTTPException(status_code=403, detail="Only admins or super admins can restore users")

    # 🚫 Ensure the user is actually deleted
    if user_to_restore.is_active:
        raise HTTPException(status_code=400, detail="User account is already active")

    # ✅ Restore user
    user_to_restore.is_active = True
    user_to_restore.deleted_at = None
    user_to_restore.deletion_reason = None

    db.commit()

    # 📝 Log activity
    log_activity(
        db=db,
        user_id=current_user.id,
        action="restore_user",
        details=f"Restored user: {user_to_restore.email} (ID: {user_to_restore.id})"
    )

    return {"message": f"User {user_to_restore.email} has been restored successfully."}

@router.get("/users/deleted", response_model=list[DeletedUser])
def get_deleted_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 🔒 Only admins or super_admins can view deleted users
    if current_user.role == "admin":
        users = (
            db.query(User)
            .filter(
                User.organization_id == current_user.organization_id,
                User.is_active == False
            )
            .all()
        )
    elif current_user.role == "super_admin":
        users = db.query(User).filter(User.is_active == False).all()
    else:
        raise HTTPException(status_code=403, detail="Not authorized to view deleted users")

    return users

@router.get("/users/deleted/{user_id}", response_model=DeletedUser)
def get_deleted_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 🔍 Fetch user
    user = db.query(User).filter(User.id == user_id, User.is_active == False).first()

    if not user:
        raise HTTPException(status_code=404, detail="Deleted user not found")

    # 🔒 Authorization
    if current_user.role == "admin" and user.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="Not authorized to view this deleted user")

    if current_user.role not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Not authorized to view deleted users")

    return user    