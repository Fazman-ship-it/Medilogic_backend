from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app import models, schemas
from app.database import get_db
from app.dependencies import require_role, get_current_user

router = APIRouter(
    prefix="/daily-notifications",
    tags=["Daily Notifications"],  # ✅ clearer tag name
)

# Super Admin can create global daily notifications
@router.post("/", response_model=schemas.DailyNotificationResponse)
def create_notification(
    notification: schemas.DailyNotificationCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    if current_user["role"] not in ["super_admin", "admin"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    db_notification = models.DailyNotification(
        subject=notification.subject,
        body=notification.body,
        is_ai_generated=False,
        organization_id=None if current_user["role"] == "super_admin" else current_user["organization_id"]
    )

    db.add(db_notification)
    db.commit()
    db.refresh(db_notification)
    return db_notification

@router.get("/", response_model=list[schemas.DailyNotificationResponse])
def list_notifications(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)  # make sure this returns a User object
):
    query = db.query(models.DailyNotification)

    if current_user.role == "admin":
        # Only see notifications for your org + global ones from super admin
        query = query.filter(
            (models.DailyNotification.organization_id == current_user.organization_id) |
            (models.DailyNotification.organization_id.is_(None))  # super admin global messages
        )

    elif current_user.role == "super_admin":
        # Super admin only sees the global notifications they made
        query = query.filter(models.DailyNotification.organization_id.is_(None))

    return query.order_by(models.DailyNotification.created_at.desc()).all()

@router.delete("/{notification_id}")
def delete_notification(
    notification_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    notification = db.query(models.DailyNotification).filter(models.DailyNotification.id == notification_id).first()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    if current_user["role"] == "super_admin":
        # Can delete only global messages
        if notification.organization_id is not None:
            raise HTTPException(status_code=403, detail="Super admin can only delete global notifications")

    elif current_user["role"] == "admin":
        # Can delete only their org’s notifications
        if notification.organization_id != current_user["organization_id"]:
            raise HTTPException(status_code=403, detail="You can only delete your own organization’s notifications")

    else:
        raise HTTPException(status_code=403, detail="Not authorized to delete notifications")

    db.delete(notification)
    db.commit()
    return {"detail": "Notification deleted successfully"}
