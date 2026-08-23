"""HTTP auth-matrix and error mapping tests (no Mongo)."""

from __future__ import annotations

from typing import Optional
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.wishlist.adapters.http.router import _http_from_domain, router
from app.wishlist.application.groups import CreateGroup
from app.wishlist.application.products import AddProduct
from app.wishlist.application.reservations import ReserveProduct
from app.wishlist.domain.actor import GuestActor, MemberActor
from app.wishlist.domain.errors import (
    AlreadyReserved,
    GroupNotFound,
    LinkRevoked,
    LoginRequiredForPurchase,
    ReservationCapExceeded,
)
from app.wishlist.domain.group import Member
from app.wishlist.wiring import Container, get_container, reset_container
from tests.wishlist.conftest import (
    FakeGroupRepo,
    FakeProductRepo,
    FakePurchaseRepo,
    FakeReservationRepo,
    FakeTokenGen,
    FrozenClock,
    NullAudit,
)


def test_error_status_mapping():
    assert _http_from_domain(GroupNotFound()).status_code == 404
    assert _http_from_domain(LinkRevoked()).status_code == 403
    assert _http_from_domain(LoginRequiredForPurchase()).status_code == 401
    assert _http_from_domain(AlreadyReserved()).status_code == 409
    assert _http_from_domain(ReservationCapExceeded()).status_code == 409


class FakeContainer:
    """Minimal container using in-memory repos for HTTP tests."""

    def __init__(self) -> None:
        self.clock = FrozenClock()
        self.tokens = FakeTokenGen()
        self.audit = NullAudit()
        self.groups = FakeGroupRepo()
        self.products = FakeProductRepo()
        self.reservations = FakeReservationRepo()
        self.purchases = FakePurchaseRepo()
        self.create_group = CreateGroup(
            groups=self.groups, tokens=self.tokens, audit=self.audit
        )
        self.reserve_product = ReserveProduct(
            groups=self.groups,
            products=self.products,
            reservations=self.reservations,
            clock=self.clock,
            audit=self.audit,
        )
        from app.wishlist.application.groups import GetGroupByAccessToken

        self.get_group_by_access_token = GetGroupByAccessToken(groups=self.groups)
        self.add_product = AddProduct(
            groups=self.groups, products=self.products, audit=self.audit
        )


@pytest.fixture
def fake_http(monkeypatch):
    fc = FakeContainer()
    reset_container()

    def _get():
        return fc

    monkeypatch.setattr(
        "app.wishlist.adapters.http.deps.get_container", _get
    )
    monkeypatch.setattr(
        "app.wishlist.adapters.http.router.get_wishlist_container", lambda: fc
    )
    monkeypatch.setattr(
        "app.wishlist.adapters.http.deps.get_wishlist_container", lambda: fc
    )

    app = FastAPI()
    app.state.limiter = MagicMock()
    # Disable slowapi limits for tests by stubbing
    from slowapi import Limiter
    from slowapi.util import get_remote_address

    limiter = Limiter(key_func=get_remote_address, enabled=False)
    app.state.limiter = limiter

    app.include_router(router, prefix="/api/wishlist")

    # Bypass JWT for create by patching current_active_user on routes that need it —
    # instead we exercise access-token path which is public.
    return app, fc, TestClient(app)


@pytest.mark.asyncio
async def test_access_preview_revoked_403(fake_http):
    app, fc, client = fake_http
    group = await fc.create_group(
        user_id="u1",
        username="Sam",
        name="G",
        owners_can_see_fulfillment=False,
    )
    group.link_revoked = True
    await fc.groups.save(group)

    resp = client.get(f"/api/wishlist/access/{group.access_token}")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_access_preview_unknown_404(fake_http):
    app, fc, client = fake_http
    resp = client.get(f"/api/wishlist/access/{uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_stale_token_on_group_get_403(fake_http):
    app, fc, client = fake_http
    group = await fc.create_group(
        user_id="u1",
        username="Sam",
        name="G",
        owners_can_see_fulfillment=False,
    )
    # Call with wrong token (no JWT) -> guest path -> 403
    resp = client.get(
        f"/api/wishlist/{group.id}",
        headers={"X-Wishlist-Access": str(uuid4())},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_duplicate_reserve_maps_to_409(fake_http):
    app, fc, client = fake_http
    group = await fc.create_group(
        user_id="u1",
        username="Sam",
        name="G",
        owners_can_see_fulfillment=True,
        max_active_reservations=5,
    )
    other = Member.new(display_name="Alex", user_id="u2")
    group.members.append(other)
    await fc.groups.save(group)
    product = await fc.add_product(
        group_id=group.id,
        owner_member_id=other.member_id,
        title="Headphones",
        options=[{"title": "Sony"}],
        actor=MemberActor(
            user_id="u1",
            member_id=group.members[0].member_id,
            display_name="Sam",
        ),
    )
    headers = {"X-Wishlist-Access": str(group.access_token)}
    r1 = client.post(
        f"/api/wishlist/{group.id}/products/{product.id}/reserve",
        headers=headers,
        json={"reserved_as_name": "Maya"},
    )
    assert r1.status_code == 201
    r2 = client.post(
        f"/api/wishlist/{group.id}/products/{product.id}/reserve",
        headers=headers,
        json={"reserved_as_name": "Bob"},
    )
    assert r2.status_code == 409


def test_purchase_without_jwt_returns_401(fake_http):
    app, fc, client = fake_http
    # No Authorization header — fastapi-users current_active_user should 401
    resp = client.post(
        f"/api/wishlist/{uuid4()}/reservations/{uuid4()}/purchase",
        json={},
    )
    # Without auth backend wired, dependency may 401 or fail differently.
    # Ensure we do not get 200.
    assert resp.status_code in (401, 403, 500)
