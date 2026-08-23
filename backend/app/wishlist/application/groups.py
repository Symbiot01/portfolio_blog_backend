"""Group use cases: create, list, get, update, delete, leave, rotate, revoke, link info."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from app.wishlist.application.ports import (
    AccessTokenGen,
    AuditSink,
    GroupRepo,
    ProductRepo,
    PurchaseRepo,
    ReservationRepo,
)
from app.wishlist.domain.errors import (
    Forbidden,
    GroupNotFound,
    LinkRevoked,
    NotLinkedMember,
    ValidationError,
)
from app.wishlist.domain.group import Group, GroupSettings, Member
from app.wishlist.domain.product import ProductStatus
from app.wishlist.domain.reservation import ReservationStatus


@dataclass
class CreateGroup:
    groups: GroupRepo
    tokens: AccessTokenGen
    audit: AuditSink

    async def __call__(
        self,
        *,
        user_id: str,
        username: str,
        name: str,
        owners_can_see_fulfillment: bool,
        description: Optional[str] = None,
        max_active_reservations: int = 2,
    ) -> Group:
        name = (name or "").strip()
        if not name:
            raise ValidationError("name is required")
        if len(name) > 100:
            raise ValidationError("name max length is 100")
        try:
            settings = GroupSettings(
                owners_can_see_fulfillment=owners_can_see_fulfillment,
                max_active_reservations=max_active_reservations,
            )
        except ValueError as e:
            raise ValidationError(str(e)) from e

        member = Member.new(display_name=username, user_id=user_id, joined_via="login")
        group = Group(
            id=None,
            name=name,
            description=description,
            access_token=self.tokens.new(),
            link_revoked=False,
            leader_member_id=member.member_id,
            settings=settings,
            members=[member],
        )
        saved = await self.groups.insert(group)
        await self.audit.record(
            group_id=saved.id or "",
            action="group.create",
            actor_user_id=user_id,
            metadata={"name": name},
        )
        return saved


@dataclass
class ListMyGroups:
    groups: GroupRepo

    async def __call__(self, *, user_id: str) -> List[Group]:
        return await self.groups.list_for_user(user_id)


@dataclass
class GetGroup:
    groups: GroupRepo

    async def __call__(self, *, group_id: str) -> Group:
        group = await self.groups.get(group_id)
        if not group:
            raise GroupNotFound("group not found")
        return group


@dataclass
class GetGroupByAccessToken:
    groups: GroupRepo

    async def __call__(self, *, access_token: str) -> Group:
        group = await self.groups.get_by_access_token(access_token)
        if not group:
            raise GroupNotFound("invalid access link")
        if group.link_revoked:
            raise LinkRevoked("access link revoked")
        return group


@dataclass
class LeaveGroup:
    groups: GroupRepo
    products: ProductRepo
    reservations: ReservationRepo
    purchases: PurchaseRepo
    audit: AuditSink

    async def __call__(self, *, group_id: str, user_id: str) -> Optional[Group]:
        group = await self.groups.get(group_id)
        if not group:
            raise GroupNotFound("group not found")
        member = group.find_linked_member_for_user(user_id)
        if not member:
            raise NotLinkedMember("not a linked member")

        was_leader = group.is_leader(member.member_id)
        # Soft unlink — keep the slot and display name
        member.user_id = None

        if was_leader:
            successor = group.pick_successor(excluding_member_id=None)
            # Prefer a still-linked member; pick_successor already prefers linked
            if successor:
                group.leader_member_id = successor.member_id
            else:
                # No members at all (shouldn't happen while member still in list)
                pass

        # If somehow members list is empty — cascade delete
        if not group.members:
            await self._cascade_delete(group_id)
            await self.audit.record(
                group_id=group_id,
                action="group.delete",
                actor_user_id=user_id,
            )
            return None

        # If no member remains with any identity and we want empty-group delete:
        # Spec: cascade when members list empty. Soft unlink keeps slots, so
        # group persists with unlinked slots. That is intentional.
        saved = await self.groups.save(group)
        await self.audit.record(
            group_id=group_id,
            action="member.leave",
            actor_user_id=user_id,
            metadata={
                "member_id": member.member_id,
                "new_leader": saved.leader_member_id if was_leader else None,
            },
        )
        if was_leader:
            await self.audit.record(
                group_id=group_id,
                action="leader.promote",
                actor_user_id=user_id,
                metadata={"leader_member_id": saved.leader_member_id},
            )
        return saved

    async def _cascade_delete(self, group_id: str) -> None:
        await self.purchases.delete_for_group(group_id)
        await self.reservations.delete_for_group(group_id)
        await self.products.delete_for_group(group_id)
        await self.groups.delete(group_id)


@dataclass
class RotateLink:
    groups: GroupRepo
    products: ProductRepo
    reservations: ReservationRepo
    tokens: AccessTokenGen
    audit: AuditSink

    async def __call__(self, *, group_id: str, user_id: str) -> Group:
        group = await self.groups.get(group_id)
        if not group:
            raise GroupNotFound("group not found")
        member = group.find_linked_member_for_user(user_id)
        if not member:
            raise NotLinkedMember("not a linked member")

        group.access_token = self.tokens.new()
        group.link_revoked = False

        # Auto-release all active guest reservations
        active = await self.reservations.list_active_for_group(group_id)
        released_product_ids: List[str] = []
        for r in active:
            if r.guest_id is None:
                continue  # member reservations survive
            r.status = ReservationStatus.RELEASED
            await self.reservations.save(r)
            released_product_ids.append(r.product_id)

        for pid in set(released_product_ids):
            still_active = await self.reservations.get_active_for_product(pid)
            if still_active is None:
                product = await self.products.get(pid)
                if product and product.status == ProductStatus.RESERVED:
                    product.status = ProductStatus.OPEN
                    await self.products.save(product)

        saved = await self.groups.save(group)
        await self.audit.record(
            group_id=group_id,
            action="link.rotate",
            actor_user_id=user_id,
            metadata={"released_guest_reservations": len(released_product_ids)},
        )
        return saved


@dataclass
class RevokeLink:
    groups: GroupRepo
    audit: AuditSink

    async def __call__(self, *, group_id: str, user_id: str) -> Group:
        group = await self.groups.get(group_id)
        if not group:
            raise GroupNotFound("group not found")
        member = group.find_linked_member_for_user(user_id)
        if not member:
            raise NotLinkedMember("not a linked member")
        group.link_revoked = True
        saved = await self.groups.save(group)
        await self.audit.record(
            group_id=group_id, action="link.revoke", actor_user_id=user_id
        )
        return saved


@dataclass
class GetLink:
    groups: GroupRepo

    async def __call__(self, *, group_id: str, user_id: str) -> Group:
        group = await self.groups.get(group_id)
        if not group:
            raise GroupNotFound("group not found")
        if not group.find_linked_member_for_user(user_id):
            raise NotLinkedMember("not a linked member")
        return group


_UNSET = object()


@dataclass
class UpdateGroup:
    """Leader-only: name, description, spoiler flag, reservation cap."""

    groups: GroupRepo
    audit: AuditSink

    async def __call__(
        self,
        *,
        group_id: str,
        user_id: str,
        name: Optional[str] = None,
        description: object = _UNSET,
        owners_can_see_fulfillment: Optional[bool] = None,
        max_active_reservations: Optional[int] = None,
    ) -> Group:
        group = await self.groups.get(group_id)
        if not group:
            raise GroupNotFound("group not found")
        member = group.find_linked_member_for_user(user_id)
        if not member:
            raise NotLinkedMember("not a linked member")
        if not group.is_leader(member.member_id):
            raise Forbidden("only the group leader can update settings")

        if name is not None:
            cleaned = name.strip()
            if not cleaned:
                raise ValidationError("name is required")
            if len(cleaned) > 100:
                raise ValidationError("name max length is 100")
            group.name = cleaned

        if description is not _UNSET:
            if description is not None and len(str(description)) > 2000:
                raise ValidationError("description max length is 2000")
            group.description = description  # type: ignore[assignment]

        spoiler = (
            owners_can_see_fulfillment
            if owners_can_see_fulfillment is not None
            else group.settings.owners_can_see_fulfillment
        )
        cap = (
            max_active_reservations
            if max_active_reservations is not None
            else group.settings.max_active_reservations
        )
        try:
            group.settings = GroupSettings(
                owners_can_see_fulfillment=spoiler,
                max_active_reservations=cap,
            )
        except ValueError as e:
            raise ValidationError(str(e)) from e

        saved = await self.groups.save(group)
        await self.audit.record(
            group_id=group_id,
            action="group.update",
            actor_user_id=user_id,
            metadata={
                "owners_can_see_fulfillment": spoiler,
                "max_active_reservations": cap,
            },
        )
        return saved


@dataclass
class DeleteGroup:
    """Leader-only cascade delete."""

    groups: GroupRepo
    products: ProductRepo
    reservations: ReservationRepo
    purchases: PurchaseRepo
    audit: AuditSink

    async def __call__(self, *, group_id: str, user_id: str) -> None:
        group = await self.groups.get(group_id)
        if not group:
            raise GroupNotFound("group not found")
        member = group.find_linked_member_for_user(user_id)
        if not member:
            raise NotLinkedMember("not a linked member")
        if not group.is_leader(member.member_id):
            raise Forbidden("only the group leader can delete the group")

        await self.purchases.delete_for_group(group_id)
        await self.reservations.delete_for_group(group_id)
        await self.products.delete_for_group(group_id)
        await self.groups.delete(group_id)
        await self.audit.record(
            group_id=group_id,
            action="group.delete",
            actor_user_id=user_id,
        )
