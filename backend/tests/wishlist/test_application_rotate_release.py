"""Rotate link auto-releases guest reservations only."""

from __future__ import annotations

import pytest

from app.wishlist.application.groups import CreateGroup, RotateLink
from app.wishlist.application.products import AddProduct
from app.wishlist.application.reservations import ReserveProduct
from app.wishlist.domain.actor import GuestActor, MemberActor
from app.wishlist.domain.group import Member
from app.wishlist.domain.product import ProductStatus
from app.wishlist.domain.reservation import ReservationStatus


@pytest.mark.asyncio
async def test_rotate_releases_guest_keeps_member(repos, clock):
    create = CreateGroup(
        groups=repos["groups"], tokens=repos["tokens"], audit=repos["audit"]
    )
    group = await create(
        user_id="u-owner",
        username="Owner",
        name="Home",
        owners_can_see_fulfillment=True,
        max_active_reservations=5,
    )
    other = Member.new(display_name="Friend", user_id="u-friend")
    group.members.append(other)
    await repos["groups"].save(group)

    add = AddProduct(
        groups=repos["groups"], products=repos["products"], audit=repos["audit"]
    )
    owner_actor = MemberActor(
        user_id="u-owner",
        member_id=group.members[0].member_id,
        display_name="Owner",
    )
    p_guest = await add(
        group_id=group.id,
        owner_member_id=other.member_id,
        title="Guest item",
        options=[{"title": "A"}],
        actor=owner_actor,
    )
    p_member = await add(
        group_id=group.id,
        owner_member_id=other.member_id,
        title="Member item",
        options=[{"title": "B"}],
        actor=owner_actor,
    )

    reserve = ReserveProduct(
        groups=repos["groups"],
        products=repos["products"],
        reservations=repos["reservations"],
        clock=clock,
        audit=repos["audit"],
    )
    await reserve(
        group_id=group.id,
        product_id=p_guest.id,
        actor=GuestActor(),
        reserved_as_name="Maya",
        guest_id_header="g1",
    )
    await reserve(
        group_id=group.id,
        product_id=p_member.id,
        actor=MemberActor(
            user_id="u-owner",
            member_id=group.members[0].member_id,
            display_name="Owner",
        ),
        reserved_as_name="Owner",
    )

    old_token = group.access_token
    rotate = RotateLink(
        groups=repos["groups"],
        products=repos["products"],
        reservations=repos["reservations"],
        tokens=repos["tokens"],
        audit=repos["audit"],
    )
    updated = await rotate(group_id=group.id, user_id="u-owner")
    assert updated.access_token != old_token

    p_guest = await repos["products"].get(p_guest.id)
    p_member = await repos["products"].get(p_member.id)
    assert p_guest.status == ProductStatus.OPEN
    assert p_member.status == ProductStatus.RESERVED

    active = await repos["reservations"].list_active_for_group(group.id)
    assert len(active) == 1
    assert active[0].actor_user_id == "u-owner"
    assert active[0].guest_id is None
