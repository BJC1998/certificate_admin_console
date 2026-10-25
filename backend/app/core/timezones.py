from datetime import UTC, datetime
from functools import lru_cache
from zoneinfo import ZoneInfo


@lru_cache(maxsize=128)
def iana_zone(name: str) -> ZoneInfo:
    return ZoneInfo(name)


def tenant_local_date(utc_timestamp: str, timezone_name: str) -> str:
    """SQLite function for calendar-date sorting using actual IANA transitions."""
    timestamp = datetime.fromisoformat(utc_timestamp)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(iana_zone(timezone_name)).date().isoformat()
