
# app/routes/applicant_analytics.py

from fastapi import APIRouter, Depends, HTTPException
from app.schemas import ApplicationAnalyticsResponse, DailyViewStat
from sqlalchemy.orm import Session
from app import models, database
from app.dependencies import get_current_user
from datetime import datetime, timedelta

router = APIRouter()

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from app import models, database
from app.schemas import (
    ApplicationAnalyticsResponse, DailyViewStat,
    PlotlyChartPayload, PlotlyTrace, PlotlyLayout
)
from app.dependencies import get_current_user

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
    Subscription-tiered analytics:
      - free: total_views only
      - green: total_views, unique_organizations, last_viewed
      - blue: full analytics + Plotly-ready chart payload
    """
    # Verify ownership
    application = (
        db.query(models.InternationalApplication)
        .filter(
            models.InternationalApplication.id == application_id,
            models.InternationalApplication.user_id == current_user.id
        )
        .first()
    )
    if not application:
        raise HTTPException(status_code=404, detail="Application not found or not owned by user")

    # Fetch views
    views = (
        db.query(models.ApplicationView)
        .filter(models.ApplicationView.application_id == application_id)
        .order_by(models.ApplicationView.viewed_at.asc())
        .all()
    )

    total_views = len(views)
    if total_views == 0:
        return ApplicationAnalyticsResponse(
            application_id=application_id,
            total_views=0,
            unique_organizations=0,
            last_viewed_at=None,
            views_over_time=[],
            extra_insights=None,
            chart=None
        )

    # Aggregate per day
    daily = {}
    for v in views:
        key = v.viewed_at.date().isoformat()
        daily[key] = daily.get(key, 0) + 1

    # Shared metrics
    unique_orgs = len({v.organization_id for v in views if v.organization_id})
    last_viewed_at = max(v.viewed_at for v in views).isoformat()

    # Determine tier (default to "free" if missing)
    subscription = getattr(current_user, "subscription_tier", "free") or "free"

    # FREE: minimal
    if subscription == "free":
        return ApplicationAnalyticsResponse(
            application_id=application_id,
            total_views=total_views,
            unique_organizations=None,
            last_viewed_at=None,
            views_over_time=[],
            extra_insights=None,
            chart=None
        )

    # GREEN: mid-level
    if subscription == "green":
        return ApplicationAnalyticsResponse(
            application_id=application_id,
            total_views=total_views,
            unique_organizations=unique_orgs,
            last_viewed_at=last_viewed_at,
            views_over_time=[],   # chart locked for green
            extra_insights=None,
            chart=None
        )

    # BLUE: full analytics + chart
    if subscription == "blue":
        # Sort days and build arrays for Plotly
        dates_sorted = sorted(daily.keys())
        counts = [daily[d] for d in dates_sorted]

        # Extra insights
        most_active_day = max(daily.items(), key=lambda kv: kv[1])[0]
        avg_views = round(total_views / len(dates_sorted), 2)

        chart_payload = PlotlyChartPayload(
            traces=[
                PlotlyTrace(
                    name="Views",
                    x=dates_sorted,
                    y=counts,
                )
            ],
            layout=PlotlyLayout()
        )

        return ApplicationAnalyticsResponse(
            application_id=application_id,
            total_views=total_views,
            unique_organizations=unique_orgs,
            last_viewed_at=last_viewed_at,
            views_over_time=[DailyViewStat(date=d, views=c) for d, c in zip(dates_sorted, counts)],
            extra_insights={
                "most_active_day": most_active_day,
                "avg_views_per_day": avg_views
            },
            chart=chart_payload
        )

    # Fallback (unknown tier)
    return ApplicationAnalyticsResponse(
        application_id=application_id,
        total_views=total_views,
        unique_organizations=None,
        last_viewed_at=None,
        views_over_time=[],
        extra_insights=None,
        chart=None
    )