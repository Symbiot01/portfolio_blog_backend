"""Actor value objects for Wishlist."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, Union


@dataclass(frozen=True)
class MemberActor:
    source: Literal["login"] = "login"
    user_id: str = ""
    member_id: str = ""
    display_name: str = ""

    @property
    def actor_key(self) -> str:
        return f"user:{self.user_id}"


@dataclass(frozen=True)
class GuestActor:
    source: Literal["quicklink"] = "quicklink"
    guest_id: Optional[str] = None
    display_name: Optional[str] = None

    @property
    def actor_key(self) -> Optional[str]:
        if self.guest_id:
            return f"guest:{self.guest_id}"
        return None


WishlistActor = Union[MemberActor, GuestActor]
