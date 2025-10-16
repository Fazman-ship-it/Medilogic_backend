from datetime import datetime
import pytz

# Set your default local timezone (Nigeria)
LOCAL_TZ = pytz.timezone("Africa/Lagos")

def to_utc(dt: datetime) -> datetime:
    """
    Convert a datetime to UTC safely.
    If naive, assume it's in LOCAL_TZ.
    Always return timezone-aware UTC datetime.
    """
    if dt is None:
        return None

    if dt.tzinfo is None:
        # Assume Nigeria local time if no tzinfo
        dt = LOCAL_TZ.localize(dt)
    else:
        # Normalize tzinfo to handle any inconsistencies
        dt = dt.astimezone(LOCAL_TZ)

    return dt.astimezone(pytz.UTC)

def to_local(dt: datetime) -> datetime:
    """
    Convert a UTC datetime to LOCAL_TZ.
    """
    if dt.tzinfo is None:
        # assume UTC if naive
        dt = pytz.UTC.localize(dt)
    return dt.astimezone(LOCAL_TZ)

def now_utc() -> datetime:
    """
    Get current time in UTC.
    """
    return datetime.utcnow().replace(tzinfo=pytz.UTC)

def now_local() -> datetime:
    """
    Get current time in LOCAL_TZ.
    """
    return datetime.now(LOCAL_TZ)