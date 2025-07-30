# app/routes/qr_code.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from fastapi.responses import JSONResponse
import qrcode
import io
import base64

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Trip, User
from app.utilites.secure_qr_token import generate_qr_token

router = APIRouter(prefix="/qr", tags=["QR Codes"])

@router.get("/generate/{trip_id}")
def generate_qr_code(trip_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    trip = db.query(Trip).filter(Trip.id == trip_id, Trip.organization_id == current_user.organization_id).first()
    if not trip:
        return JSONResponse(status_code=404, content={"detail": "Trip not found or access denied"})

    token = generate_qr_token(trip.id, trip.organization_id)
    confirmation_url = f"https://medilogic.vercel.app/confirm?token={token}"

    # Generate QR image
    qr = qrcode.make(confirmation_url)
    buffer = io.BytesIO()
    qr.save(buffer, format="PNG")
    qr_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    return {
        "trip_id": str(trip.id),
        "organization_id": str(trip.organization_id),
        "qr_token": token,
        "confirmation_url": confirmation_url,
        "qr_image_base64": qr_base64
    }