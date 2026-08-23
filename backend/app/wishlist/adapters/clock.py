"""UTC clock adapter."""

from __future__ import annotations

from datetime import datetime


class UtcClock:
    def now(self) -> datetime:
        return datetime.utcnow()
