from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from app.config import settings
from app.models import User
import secrets
import string # ✅ You imported User
from uuid import UUID
from datetime import datetime
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def serialize_for_jwt(data: dict):
    """Convert UUIDs and datetimes to strings so they're safe for JWT payloads."""
    clean = {}
    for k, v in data.items():
        if isinstance(v, UUID):
            clean[k] = str(v)
        elif isinstance(v, datetime):
            clean[k] = v.isoformat()
        else:
            clean[k] = v
    return clean

# ✅ Verify plain vs hashed password
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

# ✅ Hash a plain password
def get_password_hash(password):
    return pwd_context.hash(password)

# ✅ Authenticate user from DB
def authenticate_user(db: Session, email: str, password: str):
    user = db.query(User).filter(User.email == email).first()  # ✅ use User directly
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user

from jose import jwt
from datetime import datetime, timedelta

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = serialize_for_jwt(data).copy()  # ✅ safe copy
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = serialize_for_jwt(data).copy()  # ✅ safe copy
    expire = datetime.utcnow() + (expires_delta or timedelta(days=7))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.REFRESH_SECRET_KEY, algorithm=settings.ALGORITHM)
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

def get_organization_id_from_token(token: str):
    payload = verify_token(token)
    if payload is None:
        return None
    return payload.get("org_id")   # ✅ match login_step_2


def generate_temp_password(length: int = 10) -> str:
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))