# routes/auth.py (or a public_routes.py file)

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app import models, schemas
from app.database import get_db
from app.auth import get_password_hash
from app.utilites.logging import log_activity
from app.dependencies import get_current_user
from app.utilites.email_utilites import send_email
import secrets
from datetime import datetime, timedelta
from app.config import settings
from app.utilites.time_utilities import now_utc,to_local,to_utc
router = APIRouter(prefix="/auth", tags=["Auth"])

from fastapi import Request  # ✅ required to capture IP/User-Agent
@router.post("/signup", status_code=201)
def public_signup(
    request: Request,  # ✅ required to extract IP and User-Agent
    data: schemas.PublicUserRegister,
    db: Session = Depends(get_db)
):
    # ✅ GDPR: Ensure terms are accepted
    if not data.accept_terms:
        raise HTTPException(status_code=400, detail="You must accept the terms and privacy policy.")

    # ✅ Check email uniqueness
    if db.query(models.User).filter_by(email=data.email).first():
        raise HTTPException(status_code=400, detail="Email already registered.")

    # ✅ Match org by invite code
    org = db.query(models.Organization).filter_by(invite_code=data.invite_code).first()
    if not org:
        raise HTTPException(status_code=404, detail="Invalid organization invite code.")

    # ✅ Create secure hash and verification token
    hashed_pw = get_password_hash(data.password)
    verification_token = secrets.token_urlsafe(32)
    token_expiry = now_utc() + timedelta(hours=1)

    # ✅ Create new user (initially not verified)
    new_user = models.User(
        name=data.name,
        email=data.email,
        hashed_password=hashed_pw,
        role=data.role,
        organization_id=org.id,
        is_verified=False,
        email_verification_token=verification_token,
        token_expires_at=token_expiry
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # ✅ Send verification email
    verification_link = f"https://medilogic.vercel.app/verifyemail?token={verification_token}"
    subject = "Verify your Medilogic Email"
    email_body = f"""
    Hi {new_user.name},<br><br>

    Thank you for signing up to Medilogic.<br><br>

    Please verify your email by clicking the link below:<br>
    <a href="{verification_link}">{verification_link}</a><br><br>

    This link will expire in 1 hour.<br><br>

    If you did not sign up, you can safely ignore this message.<br><br>

    Best regards,<br>
    The Medilogic Team
    """
    send_email(
        to_email=new_user.email,
        subject=subject,
        body=email_body
    )

    # ✅ Extract IP and User-Agent for audit log
    ip = request.client.host
    user_agent = request.headers.get("user-agent", "unknown")

    # ✅ GDPR Log with full trace
    log_activity(
        db=db,
        user_id=new_user.id,
        action="public_signup",
        details=(
            f"{new_user.role} {new_user.email} registered using invite code '{data.invite_code}' "
            f"and accepted the privacy policy and terms. | IP: {ip} | User-Agent: {user_agent}"
        )
    )

    return {
        "message": f"{data.role.capitalize()} account created successfully. Please check your email to verify your account.",
        "user_id": new_user.id
    }
    
from fastapi import Request  # ✅ To capture IP and User-Agent
from app.utilites.time_utilities import now_utc,to_local,to_utc
@router.get("/verify-email")
def verify_email(
    token: str,
    request: Request,  # ✅ Inject Request for client data
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(models.User.email_verification_token == token).first()

    if not user or user.token_expires_at < now_utc():
        raise HTTPException(status_code=400, detail="Invalid or expired verification token.")

    # ✅ Mark as verified
    user.is_verified = True
    user.email_verification_token = None
    user.token_expires_at = None
    db.commit()

    # ✅ Log activity with IP and user-agent
    ip = request.client.host
    user_agent = request.headers.get("user-agent", "unknown")
    log_activity(
        db=db,
        user_id=user.id,
        action="verify_email",
        details=f"Email verified via link | IP: {ip} | User-Agent: {user_agent}"
    )

    return {"message": "✅ Email verified successfully. You can now log in."}

from fastapi import Request  # ✅ Needed to capture client info
from app.utilites.time_utilities import now_utc,to_local, to_utc
@router.post("/resend-verification-email")
def resend_verification_email(
    request: Request,  # ✅ Inject request to capture IP & headers
    data: schemas.ResendVerificationRequest,
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(models.User.email == data.email).first()

    if not user:
        raise HTTPException(status_code=404, detail="User with this email was not found.")
    
    if user.is_verified:
        raise HTTPException(status_code=400, detail="This email is already verified.")

    # ✅ Generate new token
    new_token = secrets.token_urlsafe(32)
    token_expiry = now_utc() + timedelta(hours=1)

    user.email_verification_token = new_token
    user.token_expires_at = token_expiry
    db.commit()

    # ✅ Build new link
    verification_link = f"https://medilogic.vercel.app/verifyemail?token={new_token}"

    # ✅ Send email
    subject = "Resend: Verify your Medilogic Email"
    body = f"""
    Hi {user.name},

    You requested a new email verification link.

    Please verify your email by clicking the link below:
    {verification_link}

    This link will expire in 1 hour.

    If you did not request this, you can ignore this email.

    Best regards,  
    The Medilogic Team
    """
    send_email(
        to_email=user.email,
        subject=subject,
        body=body
    )

    # ✅ Extract IP and User-Agent
    ip = request.client.host
    user_agent = request.headers.get("user-agent", "unknown")

    # ✅ GDPR / activity log with extra context
    log_activity(
        db=db,
        user_id=user.id,
        action="resend_verification_email",
        details=(
            f"Verification email resent to {user.email} | IP: {ip} | User-Agent: {user_agent}"
        )
    )

    return {"message": "A new verification email has been sent. Check your inbox or spam folder."}