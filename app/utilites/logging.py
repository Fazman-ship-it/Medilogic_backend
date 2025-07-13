from app.models import ActivityLog
from sqlalchemy.orm import Session
from app import models
def log_activity(
    db: Session,
    user_id: int,
    action: str,
    details: str,
    trip_id: int = None,
    ip_address: str = None,
    user_agent: str = None
):
    # Get the user's organization_id
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        return  # You may log this or raise an exception if needed

    log = ActivityLog(
        user_id=user_id,
        action=action,
        details=details,
        trip_id=trip_id,
        organization_id=user.organization_id,
        ip_address=ip_address,
        user_agent=user_agent
    )
    db.add(log)
    db.commit()