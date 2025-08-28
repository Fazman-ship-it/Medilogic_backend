from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from app import models, schemas
from app.database import get_db
from app.dependencies import get_current_user  # ✅ import your JWT auth dependency

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])


@router.post("/subscribe/{app_id}")
def subscribe_to_badge(
    app_id: str,
    request: schemas.SubscriptionRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # 🔎 Find the applicant’s international application
    app = db.query(models.InternationalApplication).filter_by(
        id=app_id, user_id=current_user.id
    ).first()

    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    # ✅ Activate subscription
    app.badge_type = request.badge_type
    app.subscription_status = models.SubscriptionStatus.active
    app.subscription_start_date = datetime.utcnow()
    app.subscription_end_date = datetime.utcnow() + timedelta(days=30)

    db.commit()
    db.refresh(app)

    return {
        "message": f"Subscribed successfully to {request.badge_type} badge",
        "application_id": str(app.id),
        "badge_type": app.badge_type,
        "subscription_start_date": app.subscription_start_date,
        "subscription_end_date": app.subscription_end_date,
    }

# app/routes/subscription_routes.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import date, timedelta
from app import models, database
from app.utilites.payment_processor import process_payment
from app.dependencies import get_current_user


@router.post("/renew")
def renew_subscription(
    badge_type: models.BadgeType,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Find applicant record for this user
    app = (
        db.query(models.InternationalApplication)
        .filter(models.InternationalApplication.user_id == current_user.id)
        .first()
    )

    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    # Set pricing
    if badge_type == models.BadgeType.green:
        price = 7.99
    elif badge_type == models.BadgeType.blue:
        price = 12.99
    else:
        raise HTTPException(status_code=400, detail="Invalid badge type")

    # ✅ Process payment
    payment_success = process_payment(user=current_user, amount=price)
    if not payment_success:
        raise HTTPException(status_code=402, detail="Payment failed")

    # ✅ Update subscription (30 days from today)
    app.badge_type = badge_type
    app.subscription_end_date = date.today() + timedelta(days=30)

    db.commit()
    db.refresh(app)

    return {
        "message": f"Subscription renewed successfully for {badge_type.value} badge",
        "badge_type": app.badge_type,
        "expires_on": app.subscription_end_date
    }    
    