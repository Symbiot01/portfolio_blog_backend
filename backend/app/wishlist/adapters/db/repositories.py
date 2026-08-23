"""Mongo/Beanie repository implementations for Wishlist ports."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from beanie import PydanticObjectId
from pymongo.errors import DuplicateKeyError

from app.models.user import User
from app.wishlist.adapters.db.documents import (
    GroupSettingsDoc,
    MemberDoc,
    ProductOptionDoc,
    WishlistAuditEventDoc,
    WishlistGroupDoc,
    WishlistProductDoc,
    WishlistPurchaseDoc,
    WishlistReservationDoc,
)
from app.wishlist.domain.errors import AlreadyReserved
from app.wishlist.domain.group import Group, GroupSettings, Member
from app.wishlist.domain.product import Product, ProductOption, ProductStatus
from app.wishlist.domain.purchase import Purchase
from app.wishlist.domain.reservation import Reservation, ReservationStatus


def _user_id_from_link(link: Any) -> Optional[str]:
    if link is None:
        return None
    # Resolved User document
    if hasattr(link, "id") and link.id is not None:
        return str(link.id)
    # Unresolved DBRef / Link
    ref = getattr(link, "ref", None)
    if ref is not None and getattr(ref, "id", None) is not None:
        return str(ref.id)
    return None


def _member_to_doc(m: Member) -> MemberDoc:
    user_link = None
    if m.user_id:
        from beanie import Link
        from bson import DBRef

        user_link = Link(
            DBRef(collection=User.Settings.name, id=PydanticObjectId(m.user_id)),
            document_class=User,
        )
    return MemberDoc(
        member_id=m.member_id,
        display_name=m.display_name,
        user=user_link,
        joined_via=m.joined_via,  # type: ignore[arg-type]
        created_at=m.created_at,
    )


def _member_from_doc(d: MemberDoc) -> Member:
    return Member(
        member_id=d.member_id,
        display_name=d.display_name,
        user_id=_user_id_from_link(d.user),
        joined_via=d.joined_via,
        created_at=d.created_at,
    )


def _group_to_doc(g: Group) -> WishlistGroupDoc:
    doc = WishlistGroupDoc(
        name=g.name,
        description=g.description,
        access_token=g.access_token,
        link_revoked=g.link_revoked,
        leader_member_id=g.leader_member_id,
        settings=GroupSettingsDoc(
            owners_can_see_fulfillment=g.settings.owners_can_see_fulfillment,
            max_active_reservations=g.settings.max_active_reservations,
        ),
        members=[_member_to_doc(m) for m in g.members],
    )
    if g.id:
        doc.id = PydanticObjectId(g.id)
    return doc


def _group_from_doc(d: WishlistGroupDoc) -> Group:
    return Group(
        id=str(d.id),
        name=d.name,
        description=d.description,
        access_token=d.access_token,
        link_revoked=d.link_revoked,
        leader_member_id=d.leader_member_id,
        settings=GroupSettings(
            owners_can_see_fulfillment=d.settings.owners_can_see_fulfillment,
            max_active_reservations=d.settings.max_active_reservations,
        ),
        members=[_member_from_doc(m) for m in d.members],
    )


def _option_to_doc(o: ProductOption) -> ProductOptionDoc:
    return ProductOptionDoc(
        option_id=o.option_id,
        title=o.title,
        url=o.url,
        notes=o.notes,
        price=o.price,
        currency=o.currency,
        image_url=o.image_url,
    )


def _option_from_doc(d: ProductOptionDoc) -> ProductOption:
    return ProductOption(
        option_id=d.option_id,
        title=d.title,
        url=d.url,
        notes=d.notes,
        price=d.price,
        currency=d.currency,
        image_url=d.image_url,
    )


def _product_to_doc(p: Product) -> WishlistProductDoc:
    doc = WishlistProductDoc(
        group_id=p.group_id,
        owner_member_id=p.owner_member_id,
        title=p.title,
        description=p.description,
        options=[_option_to_doc(o) for o in p.options],
        status=p.status.value,  # type: ignore[arg-type]
        created_by_actor_key=p.created_by_actor_key,
    )
    if p.id:
        doc.id = PydanticObjectId(p.id)
    return doc


def _product_from_doc(d: WishlistProductDoc) -> Product:
    return Product(
        id=str(d.id),
        group_id=d.group_id,
        owner_member_id=d.owner_member_id,
        title=d.title,
        description=d.description,
        options=[_option_from_doc(o) for o in d.options],
        status=ProductStatus(d.status),
        created_by_actor_key=d.created_by_actor_key,
    )


def _reservation_to_doc(r: Reservation) -> WishlistReservationDoc:
    doc = WishlistReservationDoc(
        product_id=r.product_id,
        group_id=r.group_id,
        status=r.status.value,  # type: ignore[arg-type]
        expires_at=r.expires_at,
        reserved_as_name=r.reserved_as_name,
        actor_user_id=r.actor_user_id,
        guest_id=r.guest_id,
    )
    if r.id:
        doc.id = PydanticObjectId(r.id)
    return doc


def _reservation_from_doc(d: WishlistReservationDoc) -> Reservation:
    return Reservation(
        id=str(d.id),
        product_id=d.product_id,
        group_id=d.group_id,
        status=ReservationStatus(d.status),
        expires_at=d.expires_at,
        reserved_as_name=d.reserved_as_name,
        actor_user_id=d.actor_user_id,
        guest_id=d.guest_id,
    )


def _purchase_to_doc(p: Purchase, group_id: str) -> WishlistPurchaseDoc:
    doc = WishlistPurchaseDoc(
        reservation_id=p.reservation_id,
        product_id=p.product_id,
        group_id=group_id,
        buyer_user_id=p.buyer_user_id,
        bought_at=p.bought_at,
        option_id=p.option_id,
    )
    if p.id:
        doc.id = PydanticObjectId(p.id)
    return doc


def _purchase_from_doc(d: WishlistPurchaseDoc) -> Purchase:
    return Purchase(
        id=str(d.id),
        reservation_id=d.reservation_id,
        product_id=d.product_id,
        buyer_user_id=d.buyer_user_id,
        bought_at=d.bought_at,
        option_id=d.option_id,
    )


class MongoGroupRepo:
    async def insert(self, group: Group) -> Group:
        doc = _group_to_doc(group)
        await doc.insert()
        return _group_from_doc(doc)

    async def get(self, group_id: str) -> Optional[Group]:
        try:
            doc = await WishlistGroupDoc.get(PydanticObjectId(group_id))
        except Exception:
            return None
        if not doc:
            return None
        return _group_from_doc(doc)

    async def get_by_access_token(self, token: str) -> Optional[Group]:
        try:
            token_uuid = UUID(str(token))
        except Exception:
            return None
        doc = await WishlistGroupDoc.find_one(WishlistGroupDoc.access_token == token_uuid)
        if not doc:
            return None
        return _group_from_doc(doc)

    async def save(self, group: Group) -> Group:
        if not group.id:
            return await self.insert(group)
        existing = await WishlistGroupDoc.get(PydanticObjectId(group.id))
        if not existing:
            return await self.insert(group)
        existing.name = group.name
        existing.description = group.description
        existing.access_token = group.access_token
        existing.link_revoked = group.link_revoked
        existing.leader_member_id = group.leader_member_id
        existing.settings = GroupSettingsDoc(
            owners_can_see_fulfillment=group.settings.owners_can_see_fulfillment,
            max_active_reservations=group.settings.max_active_reservations,
        )
        existing.members = [_member_to_doc(m) for m in group.members]
        await existing.save()
        return _group_from_doc(existing)

    async def delete(self, group_id: str) -> None:
        doc = await WishlistGroupDoc.get(PydanticObjectId(group_id))
        if doc:
            await doc.delete()

    async def list_for_user(self, user_id: str) -> List[Group]:
        oid = PydanticObjectId(user_id)
        docs = await WishlistGroupDoc.find({"members.user.$id": oid}).to_list()
        return [_group_from_doc(d) for d in docs]


class MongoProductRepo:
    async def insert(self, product: Product) -> Product:
        doc = _product_to_doc(product)
        await doc.insert()
        return _product_from_doc(doc)

    async def get(self, product_id: str) -> Optional[Product]:
        try:
            doc = await WishlistProductDoc.get(PydanticObjectId(product_id))
        except Exception:
            return None
        if not doc:
            return None
        return _product_from_doc(doc)

    async def save(self, product: Product) -> Product:
        if not product.id:
            return await self.insert(product)
        existing = await WishlistProductDoc.get(PydanticObjectId(product.id))
        if not existing:
            return await self.insert(product)
        existing.title = product.title
        existing.description = product.description
        existing.options = [_option_to_doc(o) for o in product.options]
        existing.status = product.status.value  # type: ignore[assignment]
        existing.owner_member_id = product.owner_member_id
        existing.created_by_actor_key = product.created_by_actor_key
        await existing.save()
        return _product_from_doc(existing)

    async def delete(self, product_id: str) -> None:
        doc = await WishlistProductDoc.get(PydanticObjectId(product_id))
        if doc:
            await doc.delete()

    async def list_for_group(
        self, group_id: str, *, owner_member_id: Optional[str] = None
    ) -> List[Product]:
        query: Dict[str, Any] = {"group_id": group_id}
        if owner_member_id:
            query["owner_member_id"] = owner_member_id
        docs = await WishlistProductDoc.find(query).to_list()
        return [_product_from_doc(d) for d in docs]

    async def delete_for_group(self, group_id: str) -> None:
        await WishlistProductDoc.find(WishlistProductDoc.group_id == group_id).delete()


class MongoReservationRepo:
    async def insert(self, reservation: Reservation) -> Reservation:
        doc = _reservation_to_doc(reservation)
        try:
            await doc.insert()
        except DuplicateKeyError as e:
            raise AlreadyReserved("product already reserved") from e
        return _reservation_from_doc(doc)

    async def get(self, reservation_id: str) -> Optional[Reservation]:
        try:
            doc = await WishlistReservationDoc.get(PydanticObjectId(reservation_id))
        except Exception:
            return None
        if not doc:
            return None
        return _reservation_from_doc(doc)

    async def save(self, reservation: Reservation) -> Reservation:
        if not reservation.id:
            return await self.insert(reservation)
        existing = await WishlistReservationDoc.get(PydanticObjectId(reservation.id))
        if not existing:
            return await self.insert(reservation)
        existing.status = reservation.status.value  # type: ignore[assignment]
        existing.expires_at = reservation.expires_at
        existing.reserved_as_name = reservation.reserved_as_name
        existing.actor_user_id = reservation.actor_user_id
        existing.guest_id = reservation.guest_id
        await existing.save()
        return _reservation_from_doc(existing)

    async def get_active_for_product(self, product_id: str) -> Optional[Reservation]:
        doc = await WishlistReservationDoc.find_one(
            WishlistReservationDoc.product_id == product_id,
            WishlistReservationDoc.status == "active",
        )
        if not doc:
            return None
        return _reservation_from_doc(doc)

    async def list_active_for_group(self, group_id: str) -> List[Reservation]:
        docs = await WishlistReservationDoc.find(
            WishlistReservationDoc.group_id == group_id,
            WishlistReservationDoc.status == "active",
        ).to_list()
        return [_reservation_from_doc(d) for d in docs]

    async def count_active_for_user(self, group_id: str, user_id: str) -> int:
        return await WishlistReservationDoc.find(
            WishlistReservationDoc.group_id == group_id,
            WishlistReservationDoc.actor_user_id == user_id,
            WishlistReservationDoc.status == "active",
        ).count()

    async def count_active_for_guest(self, group_id: str, guest_id: str) -> int:
        return await WishlistReservationDoc.find(
            WishlistReservationDoc.group_id == group_id,
            WishlistReservationDoc.guest_id == guest_id,
            WishlistReservationDoc.status == "active",
        ).count()

    async def delete_for_group(self, group_id: str) -> None:
        await WishlistReservationDoc.find(
            WishlistReservationDoc.group_id == group_id
        ).delete()


class MongoPurchaseRepo:
    async def insert(self, purchase: Purchase, *, group_id: str) -> Purchase:
        doc = _purchase_to_doc(purchase, group_id)
        await doc.insert()
        return _purchase_from_doc(doc)

    async def get_for_product(self, product_id: str) -> Optional[Purchase]:
        doc = await WishlistPurchaseDoc.find_one(
            WishlistPurchaseDoc.product_id == product_id
        )
        if not doc:
            return None
        return _purchase_from_doc(doc)

    async def delete_for_product(self, product_id: str) -> None:
        await WishlistPurchaseDoc.find(
            WishlistPurchaseDoc.product_id == product_id
        ).delete()

    async def delete_for_group(self, group_id: str) -> None:
        await WishlistPurchaseDoc.find(WishlistPurchaseDoc.group_id == group_id).delete()


class BestEffortAuditSink:
    async def record(
        self,
        *,
        group_id: str,
        action: str,
        actor_user_id: Optional[str] = None,
        actor_guest_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        try:
            event = WishlistAuditEventDoc(
                ts=datetime.utcnow(),
                group_id=group_id,
                action=action,
                actor_user_id=actor_user_id,
                actor_guest_id=actor_guest_id,
                metadata=metadata or {},
            )
            await event.insert()
        except Exception:
            return
