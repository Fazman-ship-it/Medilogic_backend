
import uuid
from sqlalchemy.orm import Session
from app.models import Trip

def get_organization_id_from_trip(trip_id: str, db: Session):
    trip = db.query(Trip).filter(Trip.id == uuid.UUID(trip_id)).first()
    if not trip:
        raise ValueError("Trip not found")
    return trip.organization_id