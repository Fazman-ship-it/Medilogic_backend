from datetime import datetime
import pytz

# Set your default local timezone (Nigeria)
LOCAL_TZ = pytz.timezone("Africa/Lagos")

def to_utc(dt: datetime) -> datetime:
    """
    Convert a datetime to UTC.
    If naive, assume it's in LOCAL_TZ.
    """
    if dt.tzinfo is None:
        dt = LOCAL_TZ.localize(dt)
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