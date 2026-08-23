"""Reservation domain entity."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class ReservationStatus(str, Enum):
    ACTIVE = "active"
    RELEASED = "released"
    EXPIRED = "expired"
    PURCHASED = "purchased"


@dataclass
class Reservation:
    id: Optional[str]
    product_id: str
    group_id: str
    status: ReservationStatus
    expires_at: datetime
    reserved_as_name: str
    actor_user_id: Optional[str] = None
    guest_id: Optional[str] = None

    def is_expired(self, now: datetime) -> bool:
        return self.status == ReservationStatus.ACTIVE and now > self.expires_at

    def same_actor(
        self,
        *,
        user_id: Optional[str] = None,
        guest_id: Optional[str] = None,
    ) -> bool:
        if self.actor_user_id and user_id and self.actor_user_id == user_id:
            return True
        if self.guest_id and guest_id and self.guest_id == guest_id:
            return True
        return False
