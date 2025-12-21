from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from beanie import Document
from pydantic import Field


class TripEditNonce(Document):
    """
    One-time nonce to reduce replay risk for quicklink-based edit/apply flows.
    """

    trip_id: str = Field(..., max_length=64)
    nonce: str = Field(..., max_length=128)
    purpose: str = Field(default="ai_apply", max_length=40)
    issued_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime = Field(default_factory=lambda: datetime.utcnow() + timedelta(minutes=10))
    used_at: Optional[datetime] = None

    class Settings:
        name = "trip_edit_nonces"

