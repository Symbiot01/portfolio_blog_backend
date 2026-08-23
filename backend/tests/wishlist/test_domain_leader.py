"""Domain-level Wishlist tests."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.wishlist.application.views import project_product
from app.wishlist.domain.actor import MemberActor
from app.wishlist.domain.errors import ProductFrozen
from app.wishlist.domain.group import Group, GroupSettings, Member
from app.wishlist.domain.product import Product, ProductOption, ProductStatus


def test_pick_successor_prefers_oldest_linked():
    t0 = datetime(2026, 1, 1)
    m1 = Member(
        member_id="a",
        display_name="A",
        user_id=None,
        created_at=t0,
    )
    m2 = Member(
        member_id="b",
        display_name="B",
        user_id="u2",
        created_at=t0 + timedelta(hours=1),
    )
    m3 = Member(
        member_id="c",
        display_name="C",
        user_id="u3",
        created_at=t0 + timedelta(hours=2),
    )
    group = Group(
        id="g1",
        name="G",
        description=None,
        access_token=__import__("uuid").uuid4(),
        link_revoked=False,
        leader_member_id="a",
        settings=GroupSettings(owners_can_see_fulfillment=False),
        members=[m1, m2, m3],
    )
    successor = group.pick_successor(excluding_member_id="a")
    assert successor is not None
    assert successor.member_id == "b"  # oldest linked


def test_pick_successor_falls_back_to_unlinked():
    t0 = datetime(2026, 1, 1)
    m1 = Member(member_id="a", display_name="A", user_id=None, created_at=t0)
    m2 = Member(
        member_id="b",
        display_name="B",
        user_id=None,
        created_at=t0 + timedelta(hours=1),
    )
    group = Group(
        id="g1",
        name="G",
        description=None,
        access_token=__import__("uuid").uuid4(),
        link_revoked=False,
        leader_member_id="a",
        settings=GroupSettings(owners_can_see_fulfillment=True),
        members=[m1, m2],
    )
    successor = group.pick_successor(excluding_member_id="a")
    assert successor is not None
    assert successor.member_id == "b"


def test_product_freeze_rules():
    product = Product(
        id="p1",
        group_id="g1",
        owner_member_id="m1",
        title="Headphones",
        description=None,
        options=[ProductOption.new("Sony")],
        status=ProductStatus.RESERVED,
        created_by_actor_key="user:u1",
    )
    with pytest.raises(ProductFrozen):
        product.assert_can_patch()
    with pytest.raises(ProductFrozen):
        product.assert_can_delete(is_leader=True, is_creator=True)

    product.status = ProductStatus.BOUGHT
    with pytest.raises(ProductFrozen):
        product.assert_can_patch()
    with pytest.raises(ProductFrozen):
        product.assert_can_delete(is_leader=False, is_creator=True)
    product.assert_can_delete(is_leader=True, is_creator=False)  # leader ok

    product.status = ProductStatus.OPEN
    product.assert_can_patch()
    product.assert_can_delete(is_leader=False, is_creator=True)


def test_spoiler_hides_bought_and_strips_reserved_for_owner():
    owner = MemberActor(user_id="u1", member_id="m1", display_name="Sam")
    product = Product(
        id="p1",
        group_id="g1",
        owner_member_id="m1",
        title="Headphones",
        description=None,
        options=[ProductOption.new("Sony")],
        status=ProductStatus.RESERVED,
        created_by_actor_key="user:u2",
    )
    projected = project_product(
        product,
        viewer=owner,
        owners_can_see_fulfillment=False,
        reservation_info={"reservation_id": "r1", "reserved_as_name": "Maya"},
    )
    assert projected is not None
    assert projected["status"] == "open"
    assert projected["reservation"] is None

    product.status = ProductStatus.BOUGHT
    assert (
        project_product(
            product,
            viewer=owner,
            owners_can_see_fulfillment=False,
            reservation_info=None,
        )
        is None
    )

    # Non-owner still sees fulfillment
    other = MemberActor(user_id="u2", member_id="m2", display_name="Alex")
    product.status = ProductStatus.RESERVED
    projected2 = project_product(
        product,
        viewer=other,
        owners_can_see_fulfillment=False,
        reservation_info={"reservation_id": "r1"},
    )
    assert projected2 is not None
    assert projected2["status"] == "reserved"
    assert projected2["reservation"] is not None
