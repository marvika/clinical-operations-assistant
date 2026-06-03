"""The case fixes "now" at 2025-03-16T09:00:00Z (a Sunday).

All relative-date phrases must be computed against that frozen instant, so
these boundaries are pinned exactly.
"""

from datetime import datetime, timezone

from app import clock


def test_now_is_frozen():
    assert clock.now() == datetime(2025, 3, 16, 9, 0, 0, tzinfo=timezone.utc)


def test_iso_renders_utc_offset():
    assert clock.iso(clock.now()) == "2025-03-16T09:00:00+00:00"


def test_days_from_now():
    assert clock.iso(clock.days_from_now(7)) == "2025-03-23T09:00:00+00:00"
    assert clock.iso(clock.days_from_now(-14)) == "2025-03-02T09:00:00+00:00"


def test_next_week_is_march_17_to_23():
    # 2025-03-16 is a Sunday; its ISO week is Mar 10–16, so "next week"
    # is Mon Mar 17 00:00 UTC up to (exclusive) Mon Mar 24 00:00 UTC.
    start, end = clock.next_week()
    assert clock.iso(start) == "2025-03-17T00:00:00+00:00"
    assert clock.iso(end) == "2025-03-24T00:00:00+00:00"
