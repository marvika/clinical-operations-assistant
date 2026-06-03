"""Frozen clock.

The case states: assume current date/time is always 2025-03-16T09:00:00Z.
Nothing in the app may call ``datetime.now()`` — all date math goes through
this module so the assumption lives in exactly one place.
"""

from datetime import datetime, timedelta, timezone

NOW = datetime(2025, 3, 16, 9, 0, 0, tzinfo=timezone.utc)


def now() -> datetime:
    return NOW


def iso(dt: datetime) -> str:
    """ISO-8601 with explicit +00:00 offset, matching the database format."""
    return dt.isoformat()


def days_from_now(days: int) -> datetime:
    return now() + timedelta(days=days)


def next_week() -> tuple[datetime, datetime]:
    """The Monday-to-Monday window of the ISO week after the one containing now.

    2025-03-16 is a Sunday, so "next week" is Mon 2025-03-17 00:00 UTC up to
    (exclusive) Mon 2025-03-24 00:00 UTC.
    """
    today = now().replace(hour=0, minute=0, second=0, microsecond=0)
    monday_this_week = today - timedelta(days=today.weekday())
    start = monday_this_week + timedelta(days=7)
    return start, start + timedelta(days=7)
