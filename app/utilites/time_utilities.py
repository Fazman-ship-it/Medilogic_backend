from datetime import datetime
import pytz

# Default fallback timezone
DEFAULT_TZ = pytz.timezone("Europe/London")  # you can switch to Africa/Lagos if you prefer

def get_timezone(tz_name: str = None):
    """
    Safely get a timezone object by name.
    Defaults to DEFAULT_TZ if not provided or invalid.
    """
    try:
        if tz_name:
            return pytz.timezone(tz_name)
    except pytz.UnknownTimeZoneError:
        pass
    return DEFAULT_TZ

def to_utc(dt: datetime, tz_name: str = None) -> datetime:
    """
    Convert a datetime (naive or aware) to UTC.
    """
    if dt is None:
        return None

    local_tz = get_timezone(tz_name)

    if dt.tzinfo is None:
        # Localize naive datetime to the local timezone
        dt = local_tz.localize(dt)
    else:
        dt = dt.astimezone(local_tz)

    return dt.astimezone(pytz.UTC)

def to_local(dt: datetime, tz_name: str = None) -> datetime:
    """
    Convert a UTC datetime to a specified local timezone.
    """
    if dt is None:
        return None

    local_tz = get_timezone(tz_name)

    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    return dt.astimezone(local_tz)

def now_utc() -> datetime:
    """
    Current UTC datetime (aware)
    """
    return datetime.utcnow().replace(tzinfo=pytz.UTC)

def now_local(tz_name: str = None) -> datetime:
    """
    Current datetime in the given local timezone.
    """
    local_tz = get_timezone(tz_name)
    return datetime.now(local_tz)