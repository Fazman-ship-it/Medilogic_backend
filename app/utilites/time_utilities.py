from datetime import datetime
import pytz

# ✅ Default fallback timezone (e.g., Africa/Lagos)
DEFAULT_TZ = pytz.timezone("Africa/Lagos")


def get_timezone(tz_name: str = None):
    """
    Safely get a timezone object by name.
    Defaults to Africa/Lagos if not provided or invalid.
    """
    try:
        if tz_name:
            return pytz.timezone(tz_name)
    except pytz.UnknownTimeZoneError:
        pass
    return DEFAULT_TZ


def to_utc(dt: datetime, tz_name: str = None) -> datetime:
    """
    Convert a datetime (naive or localized) to UTC safely.
    If naive, assume the provided tz_name or DEFAULT_TZ.
    """
    if dt is None:
        return None

    local_tz = get_timezone(tz_name)

    if dt.tzinfo is None:
        # Localize naive datetime to the local timezone
        dt = local_tz.localize(dt)
    else:
        # Normalize tzinfo
        dt = dt.astimezone(local_tz)

    return dt.astimezone(pytz.UTC)


def to_local(dt: datetime, tz_name: str = None) -> datetime:
    """
    Convert a UTC datetime to a specified local timezone.
    Defaults to Africa/Lagos if tz_name not provided.
    """
    if dt is None:
        return None

    local_tz = get_timezone(tz_name)
    if dt.tzinfo is None:
        # assume UTC if naive
        dt = pytz.UTC.localize(dt)
    return dt.astimezone(local_tz)


def now_utc() -> datetime:
    """
    Get current UTC datetime (aware).
    """
    return datetime.utcnow().replace(tzinfo=pytz.UTC)


def now_local(tz_name: str = None) -> datetime:
    """
    Get current datetime in the given local timezone.
    Defaults to Africa/Lagos.
    """
    local_tz = get_timezone(tz_name)
    return datetime.now(local_tz)