from sqlalchemy.orm import Session
from . import models, schemas

def create_trip(db: Session, trip: schemas.TripCreate, current_user: models.User):
    db_trip = models.Trip(
        **trip.dict(),
        organization_id=current_user.organization_id,  # ✅ Multi-tenant link
        client_id=current_user.id if current_user.role == "client" else None
    )
    db.add(db_trip)
    db.commit()
    db.refresh(db_trip)

    # ✅ Optional Audit Log
    log_activity(
        db=db,
        user_id=current_user.id,
        action="trip_created",
        details=f"User {current_user.name} created trip ID {db_trip.id}",
        trip_id=db_trip.id
    )

    return db_trip
