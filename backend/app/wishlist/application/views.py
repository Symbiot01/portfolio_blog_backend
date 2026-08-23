"""View projectors — spoiler-aware product listings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.wishlist.application.ports import GroupRepo, ProductRepo, ReservationRepo
from app.wishlist.domain.actor import MemberActor, WishlistActor
from app.wishlist.domain.errors import GroupNotFound
from app.wishlist.domain.product import Product, ProductStatus


def _option_dict(o) -> Dict[str, Any]:
    return {
        "option_id": o.option_id,
        "title": o.title,
        "url": o.url,
        "notes": o.notes,
        "price": o.price,
        "currency": o.currency,
        "image_url": o.image_url,
    }


def project_product(
    product: Product,
    *,
    viewer: Optional[WishlistActor],
    owners_can_see_fulfillment: bool,
    reservation_info: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Apply spoiler rules.

    When owners_can_see_fulfillment is False and the viewer is the list owner:
    - hide bought products entirely
    - strip reservation info and present reserved products as open
    """
    is_owner = (
        isinstance(viewer, MemberActor)
        and viewer.member_id == product.owner_member_id
    )
    spoil = is_owner and not owners_can_see_fulfillment

    if spoil and product.status == ProductStatus.BOUGHT:
        return None

    status = product.status.value
    reservation_out = reservation_info
    if spoil:
        if product.status == ProductStatus.RESERVED:
            status = ProductStatus.OPEN.value
        reservation_out = None

    return {
        "id": product.id,
        "group_id": product.group_id,
        "owner_member_id": product.owner_member_id,
        "title": product.title,
        "description": product.description,
        "options": [_option_dict(o) for o in product.options],
        "status": status,
        "created_by_actor_key": product.created_by_actor_key,
        "reservation": reservation_out,
    }


@dataclass
class ListProductsView:
    groups: GroupRepo
    products: ProductRepo
    reservations: ReservationRepo

    async def __call__(
        self,
        *,
        group_id: str,
        viewer: Optional[WishlistActor] = None,
        owner_member_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        group = await self.groups.get(group_id)
        if not group:
            raise GroupNotFound("group not found")

        items = await self.products.list_for_group(
            group_id, owner_member_id=owner_member_id
        )
        out: List[Dict[str, Any]] = []
        for p in items:
            reservation_info = None
            if p.status == ProductStatus.RESERVED and p.id:
                active = await self.reservations.get_active_for_product(p.id)
                if active:
                    reservation_info = {
                        "reservation_id": active.id,
                        "reserved_as_name": active.reserved_as_name,
                        "expires_at": active.expires_at.isoformat() + "Z"
                        if active.expires_at
                        else None,
                    }
            projected = project_product(
                p,
                viewer=viewer,
                owners_can_see_fulfillment=group.settings.owners_can_see_fulfillment,
                reservation_info=reservation_info,
            )
            if projected is not None:
                out.append(projected)
        return out
