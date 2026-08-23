"""Application ports (Protocols) for Wishlist."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol
from uuid import UUID

from app.wishlist.domain.group import Group
from app.wishlist.domain.product import Product
from app.wishlist.domain.purchase import Purchase
from app.wishlist.domain.reservation import Reservation


class Clock(Protocol):
    def now(self) -> datetime: ...


class AccessTokenGen(Protocol):
    def new(self) -> UUID: ...


class ProductPreview(Protocol):
    async def from_url(self, url: str) -> Dict[str, Any]:
        """Return a draft option dict, or raise if unavailable."""
        ...


class AuditSink(Protocol):
    async def record(
        self,
        *,
        group_id: str,
        action: str,
        actor_user_id: Optional[str] = None,
        actor_guest_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None: ...


class GroupRepo(Protocol):
    async def insert(self, group: Group) -> Group: ...

    async def get(self, group_id: str) -> Optional[Group]: ...

    async def get_by_access_token(self, token: str) -> Optional[Group]: ...

    async def save(self, group: Group) -> Group: ...

    async def delete(self, group_id: str) -> None: ...

    async def list_for_user(self, user_id: str) -> List[Group]: ...


class ProductRepo(Protocol):
    async def insert(self, product: Product) -> Product: ...

    async def get(self, product_id: str) -> Optional[Product]: ...

    async def save(self, product: Product) -> Product: ...

    async def delete(self, product_id: str) -> None: ...

    async def list_for_group(
        self, group_id: str, *, owner_member_id: Optional[str] = None
    ) -> List[Product]: ...

    async def delete_for_group(self, group_id: str) -> None: ...


class ReservationRepo(Protocol):
    async def insert(self, reservation: Reservation) -> Reservation: ...

    async def get(self, reservation_id: str) -> Optional[Reservation]: ...

    async def save(self, reservation: Reservation) -> Reservation: ...

    async def get_active_for_product(self, product_id: str) -> Optional[Reservation]: ...

    async def list_active_for_group(self, group_id: str) -> List[Reservation]: ...

    async def count_active_for_user(self, group_id: str, user_id: str) -> int: ...

    async def count_active_for_guest(self, group_id: str, guest_id: str) -> int: ...

    async def delete_for_group(self, group_id: str) -> None: ...


class PurchaseRepo(Protocol):
    async def insert(self, purchase: Purchase, *, group_id: str) -> Purchase: ...

    async def get_for_product(self, product_id: str) -> Optional[Purchase]: ...

    async def delete_for_product(self, product_id: str) -> None: ...

    async def delete_for_group(self, group_id: str) -> None: ...
