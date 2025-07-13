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

router = APIRouter(
    prefix="/users", tags=['users'])
# app/routes/user.py

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime

from app.models import User, ActivityLog
from app.dependencies import get_db, get_current_user

router = APIRouter()

@router.delete("/users/{user_id}", status_code=204)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    user_to_delete = db.query(User).filter(User.id == user_id).first()
    if not user_to_delete:
        raise HTTPException(status_code=404, detail="User not found")

    # 🚫 Check access control
    if current_user.role == "admin":
        if user_to_delete.organization_id != current_user.organization_id:
            raise HTTPException(status_code=403, detail="Cannot delete users outside your organization")
    elif current_user.role != "super_admin":
        raise HTTPException(status_code=403, detail="Only admins or super admins can delete users")

    # ✅ Log activity before deletion
    log_activity(
        db=db,
        user_id=current_user.id,  # Who performed it
        action="delete_user",
        details=f"Deleted user: {user_to_delete.email} (ID: {user_to_delete.id})",
        timestamp=datetime.utcnow(),
        organization_id=current_user.organization_id  # Logs are scoped to org
    )
    # 🗑️ Check if the user is trying to delete themselves
    if user_to_delete.id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account.")

    # 🚮 Delete the user
    db.delete(user_to_delete)
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