from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

try:
    # Python 3.9+
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore


def coerce_to_utc(dt: datetime, assume_tz: str = "UTC") -> datetime:
    """
    Convert an input datetime to an *aware* UTC datetime.

    Contract:
    - If dt is timezone-aware, convert to UTC.
    - If dt is naive, interpret it in `assume_tz` (default UTC), then convert to UTC.

    Note: MongoDB stores datetimes in UTC. We normalize at the API boundary to keep behavior consistent.
    """
    if dt.tzinfo is None:
        tz = timezone.utc
        if assume_tz and assume_tz != "UTC" and ZoneInfo is not None:
            try:
                tz = ZoneInfo(assume_tz)
            except Exception:
                tz = timezone.utc
        dt = dt.replace(tzinfo=tz)
    return dt.astimezone(timezone.utc)


def ensure_end_not_before_start(start_time: datetime, end_time: Optional[datetime]) -> None:
    if end_time is None:
        return
    if end_time < start_time:
        raise ValueError("end_time must be >= start_time")


