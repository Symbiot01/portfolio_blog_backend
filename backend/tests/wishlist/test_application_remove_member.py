"""RemoveMemberSlot frees embedded capacity (leader only)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.wishlist.application.members import RemoveMemberSlot
from app.wishlist.domain.errors import Forbidden, ValidationError
from app.wishlist.domain.group import Group, GroupSettings, Member
from app.wishlist.domain.product import Product, ProductOption, ProductStatus
from tests.wishlist.conftest import (
    FakeGroupRepo,
    FakeProductRepo,
    FakePurchaseRepo,
    FakeReservationRepo,
    NullAudit,
)


@pytest.mark.asyncio
async def test_remove_pending_invite_frees_slot():
    groups = FakeGroupRepo()
    products = FakeProductRepo()
    leader = Member.new(display_name="Sam", user_id="u1", joined_via="login")
    pending = Member.new(display_name="Pending Invite", joined_via="quicklink")
    group = Group(
        id=None,
        name="G",
        description=None,
        access_token=uuid4(),
        link_revoked=False,
        leader_member_id=leader.member_id,
        settings=GroupSettings(owners_can_see_fulfillment=True),
        members=[leader, pending],
    )
    await groups.insert(group)

    saved = await RemoveMemberSlot(
        groups=groups,
        products=products,
        reservations=FakeReservationRepo(),
        purchases=FakePurchaseRepo(),
        audit=NullAudit(),
    )(group_id=group.id or "", user_id="u1", member_id=pending.member_id)

    assert len(saved.members) == 1
    assert saved.members[0].member_id == leader.member_id


@pytest.mark.asyncio
async def test_remove_cascades_products():
    groups = FakeGroupRepo()
    products = FakeProductRepo()
    leader = Member.new(display_name="Sam", user_id="u1", joined_via="login")
    alex = Member.new(display_name="Alex", user_id="u2", joined_via="login")
    group = Group(
        id=None,
        name="G",
        description=None,
        access_token=uuid4(),
        link_revoked=False,
        leader_member_id=leader.member_id,
        settings=GroupSettings(owners_can_see_fulfillment=True),
        members=[leader, alex],
    )
    await groups.insert(group)
    await products.insert(
        Product(
            id=None,
            group_id=group.id or "",
            owner_member_id=alex.member_id,
            title="Toaster",
            description=None,
            options=[ProductOption.new(title="Store")],
            status=ProductStatus.OPEN,
            created_by_actor_key="user:u2",
        )
    )

    await RemoveMemberSlot(
        groups=groups,
        products=products,
        reservations=FakeReservationRepo(),
        purchases=FakePurchaseRepo(),
        audit=NullAudit(),
    )(group_id=group.id or "", user_id="u1", member_id=alex.member_id)

    assert await products.list_for_group(group.id or "") == []


@pytest.mark.asyncio
async def test_remove_self_forbidden():
    groups = FakeGroupRepo()
    leader = Member.new(display_name="Sam", user_id="u1", joined_via="login")
    group = Group(
        id=None,
        name="G",
        description=None,
        access_token=uuid4(),
        link_revoked=False,
        leader_member_id=leader.member_id,
        settings=GroupSettings(owners_can_see_fulfillment=True),
        members=[leader],
    )
    await groups.insert(group)

    with pytest.raises(ValidationError):
        await RemoveMemberSlot(
            groups=groups,
            products=FakeProductRepo(),
            reservations=FakeReservationRepo(),
            purchases=FakePurchaseRepo(),
            audit=NullAudit(),
        )(group_id=group.id or "", user_id="u1", member_id=leader.member_id)


@pytest.mark.asyncio
async def test_non_leader_cannot_remove():
    groups = FakeGroupRepo()
    leader = Member.new(display_name="Sam", user_id="u1", joined_via="login")
    alex = Member.new(display_name="Alex", user_id="u2", joined_via="login")
    pending = Member.new(display_name="Pending", joined_via="quicklink")
    group = Group(
        id=None,
        name="G",
        description=None,
        access_token=uuid4(),
        link_revoked=False,
        leader_member_id=leader.member_id,
        settings=GroupSettings(owners_can_see_fulfillment=True),
        members=[leader, alex, pending],
    )
    await groups.insert(group)

    with pytest.raises(Forbidden):
        await RemoveMemberSlot(
            groups=groups,
            products=FakeProductRepo(),
            reservations=FakeReservationRepo(),
            purchases=FakePurchaseRepo(),
            audit=NullAudit(),
        )(group_id=group.id or "", user_id="u2", member_id=pending.member_id)
