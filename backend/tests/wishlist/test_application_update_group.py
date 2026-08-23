"""UpdateGroup / DeleteGroup authorization tests."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.wishlist.application.groups import DeleteGroup, UpdateGroup, _UNSET
from app.wishlist.domain.errors import Forbidden, ValidationError
from app.wishlist.domain.group import Group, GroupSettings, Member
from tests.wishlist.conftest import FakeGroupRepo, FakeProductRepo, FakePurchaseRepo, FakeReservationRepo, NullAudit


@pytest.mark.asyncio
async def test_update_group_leader_can_change_spoiler_and_cap():
    groups = FakeGroupRepo()
    leader = Member.new(display_name="Sam", user_id="u1", joined_via="login")
    other = Member.new(display_name="Alex", user_id="u2", joined_via="login")
    group = Group(
        id=None,
        name="Holiday",
        description="old",
        access_token=uuid4(),
        link_revoked=False,
        leader_member_id=leader.member_id,
        settings=GroupSettings(owners_can_see_fulfillment=False, max_active_reservations=2),
        members=[leader, other],
    )
    await groups.insert(group)

    updated = await UpdateGroup(groups=groups, audit=NullAudit())(
        group_id=group.id or "",
        user_id="u1",
        name="Holiday Exchange",
        description="family",
        owners_can_see_fulfillment=True,
        max_active_reservations=3,
    )
    assert updated.name == "Holiday Exchange"
    assert updated.description == "family"
    assert updated.settings.owners_can_see_fulfillment is True
    assert updated.settings.max_active_reservations == 3


@pytest.mark.asyncio
async def test_update_group_non_leader_forbidden():
    groups = FakeGroupRepo()
    leader = Member.new(display_name="Sam", user_id="u1", joined_via="login")
    other = Member.new(display_name="Alex", user_id="u2", joined_via="login")
    group = Group(
        id=None,
        name="G",
        description=None,
        access_token=uuid4(),
        link_revoked=False,
        leader_member_id=leader.member_id,
        settings=GroupSettings(owners_can_see_fulfillment=True),
        members=[leader, other],
    )
    await groups.insert(group)

    with pytest.raises(Forbidden):
        await UpdateGroup(groups=groups, audit=NullAudit())(
            group_id=group.id or "",
            user_id="u2",
            owners_can_see_fulfillment=False,
        )


@pytest.mark.asyncio
async def test_update_group_cap_bounds():
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
        await UpdateGroup(groups=groups, audit=NullAudit())(
            group_id=group.id or "",
            user_id="u1",
            max_active_reservations=9,
        )


@pytest.mark.asyncio
async def test_delete_group_requires_leader():
    groups = FakeGroupRepo()
    products = FakeProductRepo()
    reservations = FakeReservationRepo()
    purchases = FakePurchaseRepo()
    leader = Member.new(display_name="Sam", user_id="u1", joined_via="login")
    other = Member.new(display_name="Alex", user_id="u2", joined_via="login")
    group = Group(
        id=None,
        name="G",
        description=None,
        access_token=uuid4(),
        link_revoked=False,
        leader_member_id=leader.member_id,
        settings=GroupSettings(owners_can_see_fulfillment=True),
        members=[leader, other],
    )
    await groups.insert(group)

    with pytest.raises(Forbidden):
        await DeleteGroup(
            groups=groups,
            products=products,
            reservations=reservations,
            purchases=purchases,
            audit=NullAudit(),
        )(group_id=group.id or "", user_id="u2")

    await DeleteGroup(
        groups=groups,
        products=products,
        reservations=reservations,
        purchases=purchases,
        audit=NullAudit(),
    )(group_id=group.id or "", user_id="u1")
    assert await groups.get(group.id or "") is None


@pytest.mark.asyncio
async def test_update_omits_description_when_unset():
    groups = FakeGroupRepo()
    leader = Member.new(display_name="Sam", user_id="u1", joined_via="login")
    group = Group(
        id=None,
        name="G",
        description="keep me",
        access_token=uuid4(),
        link_revoked=False,
        leader_member_id=leader.member_id,
        settings=GroupSettings(owners_can_see_fulfillment=True),
        members=[leader],
    )
    await groups.insert(group)
    updated = await UpdateGroup(groups=groups, audit=NullAudit())(
        group_id=group.id or "",
        user_id="u1",
        name="G2",
        description=_UNSET,
    )
    assert updated.description == "keep me"
