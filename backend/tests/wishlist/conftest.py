"""Shared fakes and fixtures for Wishlist unit tests."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

import pytest

from app.wishlist.domain.errors import AlreadyReserved
from app.wishlist.domain.group import Group, GroupSettings, Member
from app.wishlist.domain.product import Product, ProductStatus
from app.wishlist.domain.purchase import Purchase
from app.wishlist.domain.reservation import Reservation, ReservationStatus


class FrozenClock:
    def __init__(self, now: Optional[datetime] = None) -> None:
        self._now = now or datetime(2026, 1, 1, 12, 0, 0)

    def now(self) -> datetime:
        return self._now

    def advance(self, **kwargs) -> None:
        self._now = self._now + timedelta(**kwargs)


class FakeTokenGen:
    def __init__(self) -> None:
        self._tokens: List[UUID] = []

    def new(self) -> UUID:
        t = uuid4()
        self._tokens.append(t)
        return t


class NullAudit:
    async def record(self, **kwargs) -> None:
        return None


class FakeGroupRepo:
    def __init__(self) -> None:
        self._by_id: Dict[str, Group] = {}

    async def insert(self, group: Group) -> Group:
        group.id = group.id or str(uuid4())
        self._by_id[group.id] = group
        return group

    async def get(self, group_id: str) -> Optional[Group]:
        return self._by_id.get(group_id)

    async def get_by_access_token(self, token: str) -> Optional[Group]:
        for g in self._by_id.values():
            if str(g.access_token) == str(token):
                return g
        return None

    async def save(self, group: Group) -> Group:
        assert group.id
        self._by_id[group.id] = group
        return group

    async def delete(self, group_id: str) -> None:
        self._by_id.pop(group_id, None)

    async def list_for_user(self, user_id: str) -> List[Group]:
        return [
            g
            for g in self._by_id.values()
            if any(m.user_id == user_id for m in g.members)
        ]


class FakeProductRepo:
    def __init__(self) -> None:
        self._by_id: Dict[str, Product] = {}

    async def insert(self, product: Product) -> Product:
        product.id = product.id or str(uuid4())
        self._by_id[product.id] = product
        return product

    async def get(self, product_id: str) -> Optional[Product]:
        return self._by_id.get(product_id)

    async def save(self, product: Product) -> Product:
        assert product.id
        self._by_id[product.id] = product
        return product

    async def delete(self, product_id: str) -> None:
        self._by_id.pop(product_id, None)

    async def list_for_group(
        self, group_id: str, *, owner_member_id: Optional[str] = None
    ) -> List[Product]:
        items = [p for p in self._by_id.values() if p.group_id == group_id]
        if owner_member_id:
            items = [p for p in items if p.owner_member_id == owner_member_id]
        return items

    async def delete_for_group(self, group_id: str) -> None:
        for pid in [p.id for p in self._by_id.values() if p.group_id == group_id]:
            self._by_id.pop(pid, None)


class FakeReservationRepo:
    def __init__(self) -> None:
        self._by_id: Dict[str, Reservation] = {}

    async def insert(self, reservation: Reservation) -> Reservation:
        # Emulate partial unique index
        for r in self._by_id.values():
            if (
                r.product_id == reservation.product_id
                and r.status == ReservationStatus.ACTIVE
            ):
                raise AlreadyReserved("product already reserved")
        reservation.id = reservation.id or str(uuid4())
        self._by_id[reservation.id] = reservation
        return reservation

    async def get(self, reservation_id: str) -> Optional[Reservation]:
        return self._by_id.get(reservation_id)

    async def save(self, reservation: Reservation) -> Reservation:
        assert reservation.id
        self._by_id[reservation.id] = reservation
        return reservation

    async def get_active_for_product(self, product_id: str) -> Optional[Reservation]:
        for r in self._by_id.values():
            if r.product_id == product_id and r.status == ReservationStatus.ACTIVE:
                return r
        return None

    async def list_active_for_group(self, group_id: str) -> List[Reservation]:
        return [
            r
            for r in self._by_id.values()
            if r.group_id == group_id and r.status == ReservationStatus.ACTIVE
        ]

    async def count_active_for_user(self, group_id: str, user_id: str) -> int:
        return sum(
            1
            for r in self._by_id.values()
            if r.group_id == group_id
            and r.actor_user_id == user_id
            and r.status == ReservationStatus.ACTIVE
        )

    async def count_active_for_guest(self, group_id: str, guest_id: str) -> int:
        return sum(
            1
            for r in self._by_id.values()
            if r.group_id == group_id
            and r.guest_id == guest_id
            and r.status == ReservationStatus.ACTIVE
        )

    async def delete_for_group(self, group_id: str) -> None:
        for rid in [r.id for r in self._by_id.values() if r.group_id == group_id]:
            self._by_id.pop(rid, None)


class FakePurchaseRepo:
    def __init__(self) -> None:
        self._by_id: Dict[str, Purchase] = {}
        self._group: Dict[str, str] = {}

    async def insert(self, purchase: Purchase, *, group_id: str) -> Purchase:
        purchase.id = purchase.id or str(uuid4())
        self._by_id[purchase.id] = purchase
        self._group[purchase.id] = group_id
        return purchase

    async def get_for_product(self, product_id: str) -> Optional[Purchase]:
        for p in self._by_id.values():
            if p.product_id == product_id:
                return p
        return None

    async def delete_for_product(self, product_id: str) -> None:
        for pid in [i for i, p in self._by_id.items() if p.product_id == product_id]:
            self._by_id.pop(pid, None)
            self._group.pop(pid, None)

    async def delete_for_group(self, group_id: str) -> None:
        for pid in [
            p.id for p, gid in ((self._by_id[i], self._group[i]) for i in self._by_id)
            if gid == group_id
        ]:
            self._by_id.pop(pid, None)
            self._group.pop(pid, None)


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock()


@pytest.fixture
def repos():
    return {
        "groups": FakeGroupRepo(),
        "products": FakeProductRepo(),
        "reservations": FakeReservationRepo(),
        "purchases": FakePurchaseRepo(),
        "tokens": FakeTokenGen(),
        "audit": NullAudit(),
    }
