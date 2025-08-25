
# app/routes/applicant_analytics.py

from fastapi import APIRouter, Depends, HTTPException
from app.schemas import ApplicationAnalyticsResponse, DailyViewStat
from sqlalchemy.orm import Session
from app import models, database
from app.dependencies import get_current_user
from datetime import datetime, timedelta

router = APIRouter()

@router.get(
    "/applications/{application_id}/analytics",
    response_model=ApplicationAnalyticsResponse
)
def get_application_analytics(
    application_id: str,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Return analytics data for a specific applicant's job application,
    enriched with total views, unique organizations, and last viewed date.
    """
    # Verify user owns this application
    application = db.query(models.InternationalApplication).filter(
        models.InternationalApplication.id == application_id,
        models.InternationalApplication.user_id == current_user.id
    ).first()
    if not application:
        raise HTTPException(status_code=404, detail="Application not found or not owned by user")

    # Get all views
    views = (
        db.query(models.ApplicationView)
        .filter(models.ApplicationView.application_id == application_id)
        .order_by(models.ApplicationView.viewed_at.asc())
        .all()
    )

    if not views:
        return ApplicationAnalyticsResponse(
            application_id=application_id,
            total_views=0,
            unique_organizations=0,
            last_viewed_at=None,
            views_over_time=[]
        )

    # Daily stats
    stats = {}
    for v in views:
        day = v.viewed_at.date().isoformat()
        stats[day] = stats.get(day, 0) + 1

    # Compute enriched metrics
    total_views = len(views)
    unique_orgs = len(set(v.organization_id for v in views if v.organization_id))
    last_viewed_at = max(v.viewed_at for v in views).isoformat()

    return ApplicationAnalyticsResponse(
        application_id=application_id,
        total_views=total_views,
        unique_organizations=unique_orgs,
        last_viewed_at=last_viewed_at,
        views_over_time=[DailyViewStat(date=k, views=v) for k, v in sorted(stats.items())]
    )