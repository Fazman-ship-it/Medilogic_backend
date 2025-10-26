from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.dependencies import get_current_user
from app import models,schemas,database
from app.database import get_db
from app.schemas import UserOut, TwoFACodeRequest
from app.models import User
from app.auth import (
    authenticate_user,
    create_refresh_token,
    create_access_token,
    verify_token,
)
from app.utilites.logging import log_activity
from app.config import settings
import secrets
from fastapi import Request  # ✅ Add this import at the top
from uuid import uuid4  # ✅ Import uuid4 for generating session IDs
from app.utilites.time_utilities import now_utc,to_utc
# Set up FastAPI router
router = APIRouter()

# Setup password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
# Set up OAuth2 scheme for token retrieval

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="access/login")

@router.post("/login-step-1")
def login_step_1(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(models.User.email == form_data.username).first()

    if not user or not pwd_context.verify(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.is_verified:
        raise HTTPException(status_code=403, detail="Please verify your email before logging in.")

    # 🚨 Check if user is active
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Your account is inactive. Contact support.")

    # 🔐 Generate 4-digit code and expiry
    code = str(secrets.randbelow(10000)).zfill(4)
    expiry = now_utc() + timedelta(minutes=10)

    # 🆕 Generate session_id and expiry
    session_id = str(uuid4())
    session_expires_at = now_utc() + timedelta(minutes=10)

    # 🔐 Store in user object
    user.two_fa_code = code
    user.two_fa_expiry = expiry
    user.session_id = session_id
    user.session_expires_at = session_expires_at
    db.commit()

    # 📧 Send login code via email
    subject = "Your Medilogic Login Code"
    body = f"""
    Hi {user.name},

    Your Medilogic login code is: <b>{code}</b>

    This code will expire in 10 minutes.

    If you did not request this login, please ignore this email.

    – Medilogic Team
    """
    send_email(to_email=user.email, subject=subject, body=body)

    # 📍 Extract IP and User-Agent
    ip = request.client.host
    user_agent = request.headers.get("user-agent", "unknown")

    # 📝 Log login attempt
    log_activity(
        db=db,
        user_id=user.id,
        action="login_step_1",
        details=f"2FA login code sent | IP: {ip} | User-Agent: {user_agent}"
    )

    # ✅ Return session_id and message
    return {
        "message": "Login code sent to your email",
        "session_id": session_id
    }

from fastapi import Request  # ✅ Make sure this is imported

from uuid import uuid4
from datetime import timedelta
from app import models
from app.utilites.time_utilities import now_utc,to_utc

@router.post("/login-step-2")
def login_step_2(
    request: Request,  # ✅ Inject request object
    data: TwoFACodeRequest,
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(models.User.email == data.email).first()

    if not user or not user.two_fa_code:
        raise HTTPException(status_code=400, detail="Invalid login attempt")

    if user.two_fa_code != data.code:
        raise HTTPException(status_code=400, detail="Incorrect code")

    if user.two_fa_expiry < now_utc():
        raise HTTPException(status_code=400, detail="Code has expired")

    # ✅ Clear 2FA fields
    user.two_fa_code = None
    user.two_fa_expiry = None

    # ✅ Generate session_id and session_expires_at
    session_id = str(uuid4())
    session_expires_at = now_utc() + timedelta(hours=1)  # 1 hour expiry

    user.session_id = session_id
    user.session_expires_at = session_expires_at

    db.commit()

    # ✅ Generate Access Token
    access_token = create_access_token(data={
        "sub": str(user.id),
        "role": user.role,
        "org_id": user.organization_id  # optional for multitenancy
    })

    # ✅ Generate Refresh Token
    refresh_token = create_refresh_token(data={
        "sub": str(user.id)
    })

    # ✅ Extract IP & User-Agent
    ip = request.client.host
    user_agent = request.headers.get("user-agent", "unknown")

    # ✅ Log activity
    log_activity(
        db=db,
        user_id=user.id,
        action="login_step_2",
        details=f"2FA login successful | IP: {ip} | User-Agent: {user_agent}"
    )

    # ✅ Return all tokens + session info
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,  # ✅ include this
        "token_type": "bearer",
        "expires_in": 900,  # 15 minutes
        "session_id": session_id,
        "role": user.role
    }

from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from jose import jwt, JWTError, ExpiredSignatureError
from app.models import User
from app.schemas import Token
from app.dependencies import get_db
from app.auth import create_access_token  # your token utils

@router.post("/refresh-token", response_model=Token)
def refresh_token(refresh_token: str = Body(...), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(
            refresh_token,
            settings.REFRESH_SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid refresh token")

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")

        # Include relevant claims in the new token
        new_access_token = create_access_token(data={
            "sub": str(user.id),
            "role": user.role,
            "org_id": user.organization_id # optional, only if you use multi-tenant access
        })

        return {
            "access_token": new_access_token,
            "refresh_token": refresh_token,  # keep the existing refresh token
            "token_type": "bearer",
            "expires_in": 900  # 15 minutes
        }

    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token expired")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
        
from app.utilites.time_utilities import now_utc
from app.utilites.email_utilites import send_email  # 🔄 Import this
from fastapi import Request  # ✅ import if not already
@router.post("/request-password-reset")
def request_password_reset(
    request: Request,  # ✅ inject Request to capture IP/User-Agent
    data: schemas.PasswordResetRequest,
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(models.User.email == data.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User with that email does not exist.")

    token = secrets.token_urlsafe(32)
    expiry = now_utc() + timedelta(hours=1)

    user.password_reset_token = token
    user.reset_token_expiry = expiry
    db.commit()

    # ✅ Send token by email
    reset_link = f"https://medilogic.vercel.app/resetpassword?token={token}"
    email_body = f"""
    <p>Hello {user.name},</p>
    <p>You requested a password reset. Click the link below to reset your password:</p>
    <a href="{reset_link}">Reset Password</a>
    <p>This link will expire in 1 hour.</p>
    """

    send_email(
        to_email=user.email,
        subject="Medilogic Password Reset Request",
        body=email_body
    )

    # ✅ Extract IP/User-Agent
    ip = request.client.host
    user_agent = request.headers.get("user-agent", "unknown")

    # ✅ Log activity
    log_activity(
        db=db,
        user_id=user.id,
        action="request_password_reset",
        details=f"Password reset email sent | IP: {ip} | User-Agent: {user_agent}"
    )

    return {"message": "Password reset link sent to your email."}


@router.post("/reset-password")
def reset_password(data: schemas.PasswordResetSubmit, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.password_reset_token == data.token).first()

    if not user or user.reset_token_expiry < now_utc():
        raise HTTPException(status_code=400, detail="Invalid or expired reset token.")

    # Hash the new password
    hashed_password = pwd_context.hash(data.new_password)
    user.hashed_password = hashed_password

    # Invalidate the token
    user.password_reset_token = None
    user.reset_token_expiry = None

    db.commit()

    # ✅ Optional: log activity
    log_activity(db=db, user_id=user.id, action="password_reset", details="User reset their password")

    # ✅ Optional: send confirmation email
    send_email(
        to_email=user.email,
        subject="Your Medilogic Password Has Been Reset",
        body=f"Hello {user.name},<br>Your password was successfully changed."
    )

    return {"message": "Password has been reset successfully."}

@router.post("/change-password")
def change_password(
    request: schemas.PasswordChange,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Verify current password
    if not pwd_context.verify(request.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=400,
            detail="Current password is incorrect."
        )

    # Hash new password and update
    current_user.hashed_password = pwd_context.hash(request.new_password)
    db.commit()

    return {"message": "Password changed successfully."}    