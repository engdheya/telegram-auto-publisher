"""UTC time and deterministic backoff utilities."""

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Return timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def ensure_utc(dt: datetime | None) -> datetime | None:
    """Ensure a datetime retrieved from SQLite has UTC tzinfo."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def compute_backoff_seconds(attempt: int, base_seconds: int = 15, max_seconds: int = 900) -> int:
    """Compute bounded exponential backoff in seconds (15s, 30s, 60s, 120s...)."""
    exponent = max(0, attempt - 1)
    delay = base_seconds * (2 ** exponent)
    return min(int(delay), int(max_seconds))
