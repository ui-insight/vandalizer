"""Explicit UTC timestamps at API boundaries.

MongoDB stores UTC instants but commonly returns naive datetimes. Serializing
those directly makes browsers interpret UTC clock values as local wall time.
"""
from datetime import datetime, timezone


def utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    aware = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    return aware.astimezone(timezone.utc).isoformat()
