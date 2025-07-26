from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.dependencies import get_current_user
from app import models, database
from app.schemas import UserOut
from app.config import settings  # if you're storing secrets/settings here
from app import schemas
from app.database import get_db
from app import auth
from app.auth import authenticate_user, create_access_token
from app.utilites.logging import log_activity
import secrets
from app.schemas import TwoFACodeRequest


router = APIRouter()

# Setup password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Setup OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="access/login")

# Secret key and algorithm
SECRET_KEY = "supersecretkeyhere123" # Or hardcode a temp one for now
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30


# Utility functions
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def authenticate_user(db: Session, email: str, password: str):
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


from fastapi import Request  # ✅ Add this import at the top
from uuid import uuid4  # ✅ Import uuid4 for generating session IDs
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

    # 🔐 Generate 4-digit code and expiry
    code = str(secrets.randbelow(10000)).zfill(4)
    expiry = datetime.utcnow() + timedelta(minutes=10)

    # 🆕 Generate session_id and expiry
    session_id = str(uuid4())
    session_expires_at = datetime.utcnow() + timedelta(minutes=10)

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

    if user.two_fa_expiry < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Code has expired")

    # ✅ Clear 2FA fields
    user.two_fa_code = None
    user.two_fa_expiry = None

    # ✅ Generate session_id and session_expires_at
    session_id = str(uuid4())
    session_expires_at = datetime.utcnow() + timedelta(hours=1)  # 1 hour expiry, you can adjust

    user.session_id = session_id
    user.session_expires_at = session_expires_at

    db.commit()

    # ✅ Generate JWT
    token = create_access_token(data={"sub": user.email})

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

    return {
        "access_token": token,
        "token_type": "bearer",
        "session_id": session_id  # ✅ Return session_id as requested by frontend
    }

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
    expiry = datetime.utcnow() + timedelta(hours=1)

    user.password_reset_token = token
    user.reset_token_expiry = expiry
    db.commit()

    # ✅ Send token by email
    reset_link = f"http://localhost:300/reset-password?token={token}"
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