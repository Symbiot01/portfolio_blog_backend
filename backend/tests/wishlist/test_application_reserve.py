"""Application-level reserve / release / expire tests."""

from __future__ import annotations

import pytest

from app.wishlist.application.groups import CreateGroup
from app.wishlist.application.products import AddProduct
from app.wishlist.application.reservations import (
    RESERVATION_TTL_DAYS,
    ReleaseReservation,
    ReserveProduct,
)
from app.wishlist.domain.actor import GuestActor, MemberActor
from app.wishlist.domain.errors import (
    AlreadyReserved,
    CannotReserveOwnList,
    ReservationCapExceeded,
)
from app.wishlist.domain.product import ProductStatus
from tests.wishlist.conftest import FakeGroupRepo, FakeProductRepo, FakeReservationRepo


async def _seed_group_with_product(repos, clock):
    create = CreateGroup(
        groups=repos["groups"], tokens=repos["tokens"], audit=repos["audit"]
    )
    group = await create(
        user_id="u-owner",
        username="Owner",
        name="Home",
        owners_can_see_fulfillment=False,
        max_active_reservations=2,
    )
    # second member slot owned by someone else
    from app.wishlist.domain.group import Member

    other = Member.new(display_name="Friend", user_id="u-friend", joined_via="login")
    group.members.append(other)
    await repos["groups"].save(group)

    add = AddProduct(
        groups=repos["groups"], products=repos["products"], audit=repos["audit"]
    )
    # product on friend's list, created by owner
    product = await add(
        group_id=group.id,
        owner_member_id=other.member_id,
        title="Headphones",
        options=[{"title": "Sony"}],
        actor=MemberActor(
            user_id="u-owner",
            member_id=group.members[0].member_id,
            display_name="Owner",
        ),
    )
    return group, other, product


@pytest.mark.asyncio
async def test_first_reserve_wins(repos, clock):
    group, other, product = await _seed_group_with_product(repos, clock)
    reserve = ReserveProduct(
        groups=repos["groups"],
        products=repos["products"],
        reservations=repos["reservations"],
        clock=clock,
        audit=repos["audit"],
    )
    r1, guest_id = await reserve(
        group_id=group.id,
        product_id=product.id,
        actor=GuestActor(),
        reserved_as_name="Maya",
    )
    assert r1.id
    assert guest_id
    product = await repos["products"].get(product.id)
    assert product.status == ProductStatus.RESERVED

    with pytest.raises(AlreadyReserved):
        await reserve(
            group_id=group.id,
            product_id=product.id,
            actor=GuestActor(),
            reserved_as_name="Bob",
        )


@pytest.mark.asyncio
async def test_cannot_reserve_own_list(repos, clock):
    group, other, product = await _seed_group_with_product(repos, clock)
    # put product on owner's list
    product.owner_member_id = group.members[0].member_id
    await repos["products"].save(product)

    reserve = ReserveProduct(
        groups=repos["groups"],
        products=repos["products"],
        reservations=repos["reservations"],
        clock=clock,
        audit=repos["audit"],
    )
    with pytest.raises(CannotReserveOwnList):
        await reserve(
            group_id=group.id,
            product_id=product.id,
            actor=MemberActor(
                user_id="u-owner",
                member_id=group.members[0].member_id,
                display_name="Owner",
            ),
            reserved_as_name="Owner",
        )


@pytest.mark.asyncio
async def test_reservation_cap(repos, clock):
    create = CreateGroup(
        groups=repos["groups"], tokens=repos["tokens"], audit=repos["audit"]
    )
    group = await create(
        user_id="u-owner",
        username="Owner",
        name="Home",
        owners_can_see_fulfillment=True,
        max_active_reservations=1,
    )
    from app.wishlist.domain.group import Member

    other = Member.new(display_name="Friend", user_id="u-friend")
    group.members.append(other)
    await repos["groups"].save(group)

    add = AddProduct(
        groups=repos["groups"], products=repos["products"], audit=repos["audit"]
    )
    actor_owner = MemberActor(
        user_id="u-owner",
        member_id=group.members[0].member_id,
        display_name="Owner",
    )
    p1 = await add(
        group_id=group.id,
        owner_member_id=other.member_id,
        title="A",
        options=[{"title": "o1"}],
        actor=actor_owner,
    )
    p2 = await add(
        group_id=group.id,
        owner_member_id=other.member_id,
        title="B",
        options=[{"title": "o2"}],
        actor=actor_owner,
    )

    reserve = ReserveProduct(
        groups=repos["groups"],
        products=repos["products"],
        reservations=repos["reservations"],
        clock=clock,
        audit=repos["audit"],
    )
    guest = GuestActor()
    await reserve(
        group_id=group.id,
        product_id=p1.id,
        actor=guest,
        reserved_as_name="Maya",
        guest_id_header="guest-fixed",
    )
    with pytest.raises(ReservationCapExceeded):
        await reserve(
            group_id=group.id,
            product_id=p2.id,
            actor=guest,
            reserved_as_name="Maya",
            guest_id_header="guest-fixed",
        )


@pytest.mark.asyncio
async def test_ttl_expire_reopens_product(repos, clock):
    group, other, product = await _seed_group_with_product(repos, clock)
    reserve = ReserveProduct(
        groups=repos["groups"],
        products=repos["products"],
        reservations=repos["reservations"],
        clock=clock,
        audit=repos["audit"],
    )
    await reserve(
        group_id=group.id,
        product_id=product.id,
        actor=GuestActor(),
        reserved_as_name="Maya",
        guest_id_header="g1",
    )
    clock.advance(days=RESERVATION_TTL_DAYS + 1)

    # Second reserve after TTL should succeed (lazy expire)
    r2, _ = await reserve(
        group_id=group.id,
        product_id=product.id,
        actor=GuestActor(),
        reserved_as_name="Bob",
        guest_id_header="g2",
    )
    assert r2.id


@pytest.mark.asyncio
async def test_release_by_same_guest(repos, clock):
    group, other, product = await _seed_group_with_product(repos, clock)
    reserve = ReserveProduct(
        groups=repos["groups"],
        products=repos["products"],
        reservations=repos["reservations"],
        clock=clock,
        audit=repos["audit"],
    )
    r, guest_id = await reserve(
        group_id=group.id,
        product_id=product.id,
        actor=GuestActor(),
        reserved_as_name="Maya",
    )
    release = ReleaseReservation(
        groups=repos["groups"],
        products=repos["products"],
        reservations=repos["reservations"],
        clock=clock,
        audit=repos["audit"],
    )
    await release(
        group_id=group.id,
        reservation_id=r.id,
        actor=GuestActor(guest_id=guest_id),
        guest_id_header=guest_id,
    )
    product = await repos["products"].get(product.id)
    assert product.status == ProductStatus.OPEN
