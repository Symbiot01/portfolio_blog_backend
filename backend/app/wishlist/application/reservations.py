"""Reservation and purchase use cases."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional, Tuple

from app.wishlist.application.ports import (
    AuditSink,
    Clock,
    GroupRepo,
    ProductRepo,
    PurchaseRepo,
    ReservationRepo,
)
from app.wishlist.domain.actor import GuestActor, MemberActor, WishlistActor
from app.wishlist.domain.errors import (
    AlreadyReserved,
    CannotReserveOwnList,
    GroupNotFound,
    LoginRequiredForPurchase,
    NotReservationOwner,
    ProductNotFound,
    ProductNotPurchasable,
    ReservationCapExceeded,
    ReservationNotFound,
    ValidationError,
)
from app.wishlist.domain.product import Product, ProductStatus
from app.wishlist.domain.purchase import Purchase
from app.wishlist.domain.reservation import Reservation, ReservationStatus

RESERVATION_TTL_DAYS = 14


async def expire_if_due(
    *,
    product: Product,
    reservations: ReservationRepo,
    products: ProductRepo,
    clock: Clock,
    audit: Optional[AuditSink] = None,
) -> Optional[Reservation]:
    """If the product has an active reservation past TTL, expire it and reopen product."""
    active = await reservations.get_active_for_product(product.id or "")
    if not active:
        return None
    now = clock.now()
    if not active.is_expired(now):
        return active
    active.status = ReservationStatus.EXPIRED
    await reservations.save(active)
    if product.status == ProductStatus.RESERVED:
        product.status = ProductStatus.OPEN
        await products.save(product)
    if audit and product.group_id:
        await audit.record(
            group_id=product.group_id,
            action="expire",
            metadata={"reservation_id": active.id, "product_id": product.id},
        )
    return None


@dataclass
class ReserveProduct:
    groups: GroupRepo
    products: ProductRepo
    reservations: ReservationRepo
    clock: Clock
    audit: AuditSink

    async def __call__(
        self,
        *,
        group_id: str,
        product_id: str,
        actor: WishlistActor,
        reserved_as_name: Optional[str] = None,
        guest_id_header: Optional[str] = None,
    ) -> Tuple[Reservation, Optional[str]]:
        """
        Returns (reservation, issued_guest_id_or_None).
        issued_guest_id is set when a new guest_id was created.
        """
        group = await self.groups.get(group_id)
        if not group:
            raise GroupNotFound("group not found")
        product = await self.products.get(product_id)
        if not product or product.group_id != group_id:
            raise ProductNotFound("product not found")

        await expire_if_due(
            product=product,
            reservations=self.reservations,
            products=self.products,
            clock=self.clock,
            audit=self.audit,
        )
        # reload status after possible expire
        product = await self.products.get(product_id) or product

        if product.status != ProductStatus.OPEN:
            raise AlreadyReserved("product is not available to reserve")

        if isinstance(actor, MemberActor) and actor.member_id == product.owner_member_id:
            raise CannotReserveOwnList("cannot reserve a product on your own list")

        issued_guest_id: Optional[str] = None
        actor_user_id: Optional[str] = None
        guest_id: Optional[str] = None
        name: str

        if isinstance(actor, MemberActor):
            actor_user_id = actor.user_id
            name = (reserved_as_name or actor.display_name or "").strip()
            if not name:
                raise ValidationError("reserved_as_name is required")
            count = await self.reservations.count_active_for_user(group_id, actor_user_id)
            if count >= group.settings.max_active_reservations:
                raise ReservationCapExceeded("reservation cap exceeded")
        else:
            name = (reserved_as_name or "").strip()
            if not name:
                raise ValidationError("reserved_as_name is required for guests")
            guest_id = guest_id_header or actor.guest_id
            if not guest_id:
                guest_id = secrets.token_urlsafe(32)
                issued_guest_id = guest_id
            count = await self.reservations.count_active_for_guest(group_id, guest_id)
            if count >= group.settings.max_active_reservations:
                raise ReservationCapExceeded("reservation cap exceeded")

        reservation = Reservation(
            id=None,
            product_id=product_id,
            group_id=group_id,
            status=ReservationStatus.ACTIVE,
            expires_at=self.clock.now() + timedelta(days=RESERVATION_TTL_DAYS),
            reserved_as_name=name[:100],
            actor_user_id=actor_user_id,
            guest_id=guest_id,
        )
        saved = await self.reservations.insert(reservation)
        product.status = ProductStatus.RESERVED
        await self.products.save(product)

        await self.audit.record(
            group_id=group_id,
            action="reserve",
            actor_user_id=actor_user_id,
            actor_guest_id=guest_id,
            metadata={"product_id": product_id, "reservation_id": saved.id},
        )
        return saved, issued_guest_id


@dataclass
class ReleaseReservation:
    groups: GroupRepo
    products: ProductRepo
    reservations: ReservationRepo
    clock: Clock
    audit: AuditSink

    async def __call__(
        self,
        *,
        group_id: str,
        reservation_id: str,
        actor: WishlistActor,
        guest_id_header: Optional[str] = None,
    ) -> Reservation:
        reservation = await self.reservations.get(reservation_id)
        if not reservation or reservation.group_id != group_id:
            raise ReservationNotFound("reservation not found")

        user_id = actor.user_id if isinstance(actor, MemberActor) else None
        guest_id = None
        if isinstance(actor, GuestActor):
            guest_id = guest_id_header or actor.guest_id
        elif guest_id_header:
            guest_id = guest_id_header

        if not reservation.same_actor(user_id=user_id, guest_id=guest_id):
            raise NotReservationOwner("only the reserver can release this reservation")

        if reservation.status != ReservationStatus.ACTIVE:
            raise ProductNotPurchasable("reservation is not active")

        # expire check
        if reservation.is_expired(self.clock.now()):
            reservation.status = ReservationStatus.EXPIRED
            await self.reservations.save(reservation)
            product = await self.products.get(reservation.product_id)
            if product and product.status == ProductStatus.RESERVED:
                product.status = ProductStatus.OPEN
                await self.products.save(product)
            raise ProductNotPurchasable("reservation has expired")

        reservation.status = ReservationStatus.RELEASED
        await self.reservations.save(reservation)
        product = await self.products.get(reservation.product_id)
        if product and product.status == ProductStatus.RESERVED:
            product.status = ProductStatus.OPEN
            await self.products.save(product)

        await self.audit.record(
            group_id=group_id,
            action="release",
            actor_user_id=user_id,
            actor_guest_id=guest_id,
            metadata={"reservation_id": reservation_id},
        )
        return reservation


@dataclass
class PurchaseReservation:
    groups: GroupRepo
    products: ProductRepo
    reservations: ReservationRepo
    purchases: PurchaseRepo
    clock: Clock
    audit: AuditSink

    async def __call__(
        self,
        *,
        group_id: str,
        reservation_id: str,
        user_id: str,
        guest_id_header: Optional[str] = None,
        option_id: Optional[str] = None,
    ) -> Purchase:
        if not user_id:
            raise LoginRequiredForPurchase("login required to mark bought")

        reservation = await self.reservations.get(reservation_id)
        if not reservation or reservation.group_id != group_id:
            raise ReservationNotFound("reservation not found")

        product = await self.products.get(reservation.product_id)
        if not product:
            raise ProductNotFound("product not found")

        await expire_if_due(
            product=product,
            reservations=self.reservations,
            products=self.products,
            clock=self.clock,
            audit=self.audit,
        )
        reservation = await self.reservations.get(reservation_id) or reservation

        if reservation.status != ReservationStatus.ACTIVE:
            raise ProductNotPurchasable("reservation is not active")
        if reservation.is_expired(self.clock.now()):
            raise ProductNotPurchasable("reservation has expired")

        # Guest claim path
        if (
            reservation.actor_user_id is None
            and reservation.guest_id
            and guest_id_header
            and reservation.guest_id == guest_id_header
        ):
            reservation.actor_user_id = user_id
            await self.reservations.save(reservation)

        if reservation.actor_user_id != user_id:
            raise NotReservationOwner("only the reserver can mark this bought")

        reservation.status = ReservationStatus.PURCHASED
        await self.reservations.save(reservation)
        product.status = ProductStatus.BOUGHT
        await self.products.save(product)

        purchase = Purchase(
            id=None,
            reservation_id=reservation_id,
            product_id=product.id or "",
            buyer_user_id=user_id,
            bought_at=self.clock.now(),
            option_id=option_id,
        )
        saved = await self.purchases.insert(purchase, group_id=group_id)
        await self.audit.record(
            group_id=group_id,
            action="purchase",
            actor_user_id=user_id,
            metadata={"reservation_id": reservation_id, "product_id": product.id},
        )
        return saved
