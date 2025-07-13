from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from app import models
from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ✅ Verify plain vs hashed password
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

# ✅ Hash a plain password
def get_password_hash(password):
    return pwd_context.hash(password)

# ✅ Authenticate user from DB
def authenticate_user(db: Session, email: str, password: str):
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user

# ✅ Create access token with full claims (including org_id)
def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=30))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

# ✅ Decode/verify token safely
def verify_token(token: str):
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None

# ✅ Extract email
def get_email_from_token(token: str):
    payload = verify_token(token)
    if payload is None:
        return None
    return payload.get("sub")

# ✅ Extract user ID
def get_user_id_from_token(token: str):
    payload = verify_token(token)
    if payload is None:
        return None
    return payload.get("user_id")

# ✅ Extract role
def get_user_role_from_token(token: str):
    payload = verify_token(token)
    if payload is None:
        return None
    return payload.get("role")

# ✅ Extract name
def get_user_name_from_token(token: str):
    payload = verify_token(token)
    if payload is None:
        return None
    return payload.get("name")

# ✅ ✅ NEW: Extract organization ID
def get_organization_id_from_token(token: str):
    payload = verify_token(token)
    if payload is None:
        return None
    return payload.get("organization_id")