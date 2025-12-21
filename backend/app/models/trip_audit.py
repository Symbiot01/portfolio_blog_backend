from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Literal

from beanie import Document
from pydantic import Field


class TripAuditEvent(Document):
    ts: datetime = Field(default_factory=datetime.utcnow)
    trip_id: str = Field(..., max_length=64)
    source: Literal["login", "quicklink"] = "login"
    actor_user_id: Optional[str] = Field(default=None, max_length=64)
    actor_member_id: Optional[str] = Field(default=None, max_length=64)
    action: str = Field(..., max_length=80)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    client_ip: Optional[str] = Field(default=None, max_length=64)

    class Settings:
        name = "trip_audit_events"


