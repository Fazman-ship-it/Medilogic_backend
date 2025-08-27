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

from app.models import User, ActivityLog
from app.dependencies import get_db, get_current_user
from app.schemas import UserUpdate, DeleteAccountRequest
from app.utilites.logging import log_activity

router = APIRouter(
    prefix="/users", tags=['users'])
# app/routes/user.py

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

    # 📝 Log before deletion (include reason)
    log_activity(
        db=db,
        user_id=current_user.id,
        action="delete_own_account",
        details=f"User {current_user.email} deleted their own account. Reason: {request.reason}",
        timestamp=datetime.utcnow(),
        organization_id=current_user.organization_id
    )

    # 🚮 Delete user
    db.delete(current_user)
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