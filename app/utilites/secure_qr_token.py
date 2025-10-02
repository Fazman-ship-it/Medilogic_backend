# app/utils/secure_qr_token.py

import jwt
from datetime import datetime, timedelta
from uuid import UUID
from typing import Optional
from app.utilites.time_utilities import now_utc

from fastapi import HTTPException, status
from app.config import settings  # your secret key here

SECRET_KEY = settings.SECRET_KEY  # must be present in .env
ALGORITHM = "HS256"
QR_TOKEN_EXPIRE_MINUTES = 10

def generate_qr_token(trip_id: UUID, organization_id: UUID) -> str:
    expire = now_utc() + timedelta(minutes=QR_TOKEN_EXPIRE_MINUTES)
    to_encode = {
        "trip_id": str(trip_id),
        "organization_id": str(organization_id),
        "exp": expire
    }
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_qr_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="QR code token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid QR code token")