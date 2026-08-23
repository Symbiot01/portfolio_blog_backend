"""Purchase + guest claim tests."""

from __future__ import annotations

import pytest

from app.wishlist.application.groups import CreateGroup
from app.wishlist.application.products import AddProduct
from app.wishlist.application.reservations import PurchaseReservation, ReserveProduct
from app.wishlist.domain.actor import GuestActor, MemberActor
from app.wishlist.domain.errors import LoginRequiredForPurchase, NotReservationOwner
from app.wishlist.domain.group import Member
from app.wishlist.domain.product import ProductStatus
from app.wishlist.domain.reservation import ReservationStatus


async def _setup(repos, clock):
    create = CreateGroup(
        groups=repos["groups"], tokens=repos["tokens"], audit=repos["audit"]
    )
    group = await create(
        user_id="u-owner",
        username="Owner",
        name="Home",
        owners_can_see_fulfillment=True,
    )
    other = Member.new(display_name="Friend", user_id="u-friend")
    group.members.append(other)
    await repos["groups"].save(group)
    add = AddProduct(
        groups=repos["groups"], products=repos["products"], audit=repos["audit"]
    )
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
    return group, product


@pytest.mark.asyncio
async def test_guest_claim_then_purchase(repos, clock):
    group, product = await _setup(repos, clock)
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
    purchase_uc = PurchaseReservation(
        groups=repos["groups"],
        products=repos["products"],
        reservations=repos["reservations"],
        purchases=repos["purchases"],
        clock=clock,
        audit=repos["audit"],
    )
    purchase = await purchase_uc(
        group_id=group.id,
        reservation_id=r.id,
        user_id="u-buyer",
        guest_id_header=guest_id,
    )
    assert purchase.id
    product = await repos["products"].get(product.id)
    assert product.status == ProductStatus.BOUGHT
    r = await repos["reservations"].get(r.id)
    assert r.status == ReservationStatus.PURCHASED
    assert r.actor_user_id == "u-buyer"


@pytest.mark.asyncio
async def test_purchase_wrong_user_forbidden(repos, clock):
    group, product = await _setup(repos, clock)
    reserve = ReserveProduct(
        groups=repos["groups"],
        products=repos["products"],
        reservations=repos["reservations"],
        clock=clock,
        audit=repos["audit"],
    )
    r, _ = await reserve(
        group_id=group.id,
        product_id=product.id,
        actor=MemberActor(user_id="u-friend", member_id="x", display_name="F"),
        reserved_as_name="Friend",
    )
    # Override: friend reserved while being a member of other list - just set actor
    r.actor_user_id = "u-friend"
    await repos["reservations"].save(r)

    purchase_uc = PurchaseReservation(
        groups=repos["groups"],
        products=repos["products"],
        reservations=repos["reservations"],
        purchases=repos["purchases"],
        clock=clock,
        audit=repos["audit"],
    )
    with pytest.raises(NotReservationOwner):
        await purchase_uc(
            group_id=group.id,
            reservation_id=r.id,
            user_id="u-other",
        )


@pytest.mark.asyncio
async def test_purchase_requires_user_id(repos, clock):
    group, product = await _setup(repos, clock)
    purchase_uc = PurchaseReservation(
        groups=repos["groups"],
        products=repos["products"],
        reservations=repos["reservations"],
        purchases=repos["purchases"],
        clock=clock,
        audit=repos["audit"],
    )
    with pytest.raises(LoginRequiredForPurchase):
        await purchase_uc(
            group_id=group.id,
            reservation_id="x",
            user_id="",
        )
