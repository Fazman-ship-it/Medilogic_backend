# app/utils/subscription_utils.py
# app/utils/subscription_utils.py
from datetime import datetime, timedelta
from app.schemas import SubscriptionPlan, SubscriptionStatus

# app/utils/subscription_utils.py
from datetime import datetime, timedelta
from app.schemas import SubscriptionPlan, SubscriptionStatus, BadgeType

def start_subscription(medilogic_driver, plan: SubscriptionPlan, months: int = 1):
    """
    Start or renew a subscription for a Medilogic driver.
    Auto-assign badge based on plan.
    """
    now = datetime.utcnow()
    
    # Determine start date
    if medilogic_driver.subscription_status == SubscriptionStatus.active and medilogic_driver.subscription_end:
        start_date = medilogic_driver.subscription_end
    else:
        start_date = now

    # Update subscription details
    medilogic_driver.subscription_plan = plan
    medilogic_driver.subscription_status = SubscriptionStatus.active
    medilogic_driver.subscription_start = start_date
    medilogic_driver.subscription_end = start_date + timedelta(days=30*months)

    # Auto-assign badge based on plan
    if plan == SubscriptionPlan.green:
        medilogic_driver.badge_type = BadgeType.green
    elif plan == SubscriptionPlan.blue:
        medilogic_driver.badge_type = BadgeType.blue
    else:
        medilogic_driver.badge_type = BadgeType.none

    return medilogic_driver

def check_subscription_status(medilogic_driver):
    """
    Update subscription_status based on subscription_end.
    Downgrade badge if expired.
    """
    now = datetime.utcnow()
    if medilogic_driver.subscription_end and medilogic_driver.subscription_end < now:
        medilogic_driver.subscription_status = SubscriptionStatus.expired
        medilogic_driver.subscription_plan = SubscriptionPlan.free
        medilogic_driver.badge_type = BadgeType.none
    return medilogic_driver

# app/utils/subscription_utils.py
from datetime import datetime, timedelta
from app.schemas import SubscriptionPlan, SubscriptionStatus

def start_subscription(medilogic_driver, plan: SubscriptionPlan, months: int = 1):
    """
    Start or renew a subscription for a Medilogic driver.
    - Adds remaining days if renewing early (prorated)
    - Auto-assigns badge based on plan
    """
    now = datetime.utcnow()

    # Determine start date: extend from current subscription_end if active
    if medilogic_driver.subscription_status == SubscriptionStatus.active and medilogic_driver.subscription_end:
        # Calculate remaining days
        remaining_days = (medilogic_driver.subscription_end - now).days
        start_date = now
    else:
        remaining_days = 0
        start_date = now

    # Calculate end date: full months + remaining days
    total_days = 30 * months + remaining_days
    medilogic_driver.subscription_start = start_date
    medilogic_driver.subscription_end = start_date + timedelta(days=total_days)

    # Update plan and status
    medilogic_driver.subscription_plan = plan
    medilogic_driver.subscription_status = SubscriptionStatus.active

    # Auto-assign badge based on plan
    if plan == SubscriptionPlan.green:
        medilogic_driver.badge_type = "green"
    elif plan == SubscriptionPlan.blue:
        medilogic_driver.badge_type = "blue"
    else:
        medilogic_driver.badge_type = "none"

    return medilogic_driver