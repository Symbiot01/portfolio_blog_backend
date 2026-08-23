"""Product use cases with strict lifecycle freeze rules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.wishlist.application.ports import AuditSink, GroupRepo, ProductRepo
from app.wishlist.domain.actor import GuestActor, MemberActor, WishlistActor
from app.wishlist.domain.errors import (
    Forbidden,
    GroupNotFound,
    MemberNotFound,
    ProductFrozen,
    ProductNotFound,
    ValidationError,
)
from app.wishlist.domain.product import Product, ProductOption, ProductStatus


def _actor_key(actor: WishlistActor) -> str:
    if isinstance(actor, MemberActor):
        return actor.actor_key
    if isinstance(actor, GuestActor) and actor.guest_id:
        return f"guest:{actor.guest_id}"
    raise ValidationError("guest_id required to create a product as guest")


def _parse_options(raw: List[Dict[str, Any]]) -> List[ProductOption]:
    options: List[ProductOption] = []
    for item in raw:
        title = (item.get("title") or "").strip()
        if not title:
            raise ValidationError("each option requires a title")
        url = item.get("url")
        if url is not None and len(str(url)) > 2000:
            raise ValidationError("option url max length is 2000")
        options.append(
            ProductOption.new(
                title=title,
                url=item.get("url"),
                notes=item.get("notes"),
                price=item.get("price"),
                currency=item.get("currency"),
                image_url=item.get("image_url"),
            )
        )
    Product.validate_options(options)
    return options


@dataclass
class AddProduct:
    groups: GroupRepo
    products: ProductRepo
    audit: AuditSink

    async def __call__(
        self,
        *,
        group_id: str,
        owner_member_id: str,
        title: str,
        options: List[Dict[str, Any]],
        actor: WishlistActor,
        description: Optional[str] = None,
    ) -> Product:
        group = await self.groups.get(group_id)
        if not group:
            raise GroupNotFound("group not found")
        if not group.find_member(owner_member_id):
            raise MemberNotFound("owner member not found")

        title = (title or "").strip()
        if not title:
            raise ValidationError("title is required")
        if len(title) > 150:
            raise ValidationError("title max length is 150")

        parsed = _parse_options(options)
        product = Product(
            id=None,
            group_id=group_id,
            owner_member_id=owner_member_id,
            title=title,
            description=description,
            options=parsed,
            status=ProductStatus.OPEN,
            created_by_actor_key=_actor_key(actor),
        )
        saved = await self.products.insert(product)
        await self.audit.record(
            group_id=group_id,
            action="product.create",
            actor_user_id=actor.user_id if isinstance(actor, MemberActor) else None,
            actor_guest_id=actor.guest_id if isinstance(actor, GuestActor) else None,
            metadata={"product_id": saved.id, "owner_member_id": owner_member_id},
        )
        return saved


@dataclass
class UpdateProduct:
    groups: GroupRepo
    products: ProductRepo
    audit: AuditSink

    async def __call__(
        self,
        *,
        group_id: str,
        product_id: str,
        actor: WishlistActor,
        title: Optional[str] = None,
        description: Optional[str] = None,
        options: Optional[List[Dict[str, Any]]] = None,
    ) -> Product:
        group = await self.groups.get(group_id)
        if not group:
            raise GroupNotFound("group not found")
        product = await self.products.get(product_id)
        if not product or product.group_id != group_id:
            raise ProductNotFound("product not found")

        product.assert_can_patch()

        is_leader = False
        is_creator = False
        if isinstance(actor, MemberActor):
            is_leader = group.is_leader(actor.member_id)
            is_creator = product.created_by_actor_key == actor.actor_key
        elif isinstance(actor, GuestActor) and actor.guest_id:
            is_creator = product.created_by_actor_key == f"guest:{actor.guest_id}"

        if not (is_leader or is_creator):
            raise Forbidden("only creator or leader can update this product")

        if title is not None:
            title = title.strip()
            if not title:
                raise ValidationError("title cannot be empty")
            product.title = title
        if description is not None:
            product.description = description
        if options is not None:
            product.options = _parse_options(options)

        saved = await self.products.save(product)
        await self.audit.record(
            group_id=group_id,
            action="product.update",
            actor_user_id=actor.user_id if isinstance(actor, MemberActor) else None,
            actor_guest_id=actor.guest_id if isinstance(actor, GuestActor) else None,
            metadata={"product_id": product_id},
        )
        return saved


@dataclass
class DeleteProduct:
    groups: GroupRepo
    products: ProductRepo
    audit: AuditSink

    async def __call__(
        self,
        *,
        group_id: str,
        product_id: str,
        actor: WishlistActor,
    ) -> None:
        group = await self.groups.get(group_id)
        if not group:
            raise GroupNotFound("group not found")
        product = await self.products.get(product_id)
        if not product or product.group_id != group_id:
            raise ProductNotFound("product not found")

        is_leader = False
        is_creator = False
        if isinstance(actor, MemberActor):
            is_leader = group.is_leader(actor.member_id)
            is_creator = product.created_by_actor_key == actor.actor_key
        elif isinstance(actor, GuestActor) and actor.guest_id:
            is_creator = product.created_by_actor_key == f"guest:{actor.guest_id}"

        product.assert_can_delete(is_leader=is_leader, is_creator=is_creator)
        await self.products.delete(product_id)
        await self.audit.record(
            group_id=group_id,
            action="product.delete",
            actor_user_id=actor.user_id if isinstance(actor, MemberActor) else None,
            actor_guest_id=actor.guest_id if isinstance(actor, GuestActor) else None,
            metadata={"product_id": product_id},
        )
