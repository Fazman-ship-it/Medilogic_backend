# app/utils/token_utils.py

import jwt
from datetime import datetime, timedelta
from app.config import settings
from app.utilites.time_utilities import now_utc

def generate_delivery_token(trip_id: str, organization_id: str):
    payload = {
        "trip_id": trip_id,
        "org_id": organization_id,
        "exp": now_utc() + timedelta(minutes=settings.DELIVERY_CONFIRM_EXPIRY_MINUTES)
    }
    token = jwt.encode(payload, settings.DELIVERY_CONFIRM_SECRET, algorithm="HS256")
    return token