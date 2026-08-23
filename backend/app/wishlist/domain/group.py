"""Group, member, and settings domain entities."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from uuid import UUID, uuid4


MAX_MEMBERS = 20


@dataclass
class GroupSettings:
    owners_can_see_fulfillment: bool
    max_active_reservations: int = 2

    def __post_init__(self) -> None:
        if not (1 <= self.max_active_reservations <= 5):
            raise ValueError("max_active_reservations must be between 1 and 5")


@dataclass
class Member:
    member_id: str
    display_name: str
    user_id: Optional[str] = None
    joined_via: str = "login"  # "login" | "quicklink"
    created_at: datetime = field(default_factory=datetime.utcnow)

    @classmethod
    def new(
        cls,
        display_name: str,
        *,
        user_id: Optional[str] = None,
        joined_via: str = "login",
        created_at: Optional[datetime] = None,
    ) -> "Member":
        return cls(
            member_id=str(uuid4()),
            display_name=display_name,
            user_id=user_id,
            joined_via=joined_via,
            created_at=created_at or datetime.utcnow(),
        )


@dataclass
class Group:
    id: Optional[str]
    name: str
    description: Optional[str]
    access_token: UUID
    link_revoked: bool
    leader_member_id: str
    settings: GroupSettings
    members: List[Member]

    def find_member(self, member_id: str) -> Optional[Member]:
        return next((m for m in self.members if m.member_id == member_id), None)

    def find_linked_member_for_user(self, user_id: str) -> Optional[Member]:
        return next((m for m in self.members if m.user_id == user_id), None)

    def is_leader(self, member_id: str) -> bool:
        return self.leader_member_id == member_id

    def pick_successor(self, excluding_member_id: Optional[str] = None) -> Optional[Member]:
        """
        Promote oldest remaining linked member; if none linked, oldest remaining slot.
        """
        candidates = [m for m in self.members if m.member_id != excluding_member_id]
        if not candidates:
            return None
        linked = [m for m in candidates if m.user_id]
        pool = linked if linked else candidates
        return min(pool, key=lambda m: m.created_at)
