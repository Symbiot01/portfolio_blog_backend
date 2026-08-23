"""Member use cases: add slot, link-self, leader unlink."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.wishlist.application.ports import (
    AuditSink,
    GroupRepo,
    ProductRepo,
    PurchaseRepo,
    ReservationRepo,
)
from app.wishlist.domain.errors import (
    Forbidden,
    GroupNotFound,
    MemberNotFound,
    MembersCapExceeded,
    NotLinkedMember,
    ValidationError,
)
from app.wishlist.domain.group import MAX_MEMBERS, Member
from app.wishlist.domain.reservation import ReservationStatus


@dataclass
class AddMemberSlot:
    groups: GroupRepo
    audit: AuditSink

    async def __call__(
        self,
        *,
        group_id: str,
        display_name: str,
        actor_user_id: Optional[str] = None,
        actor_guest_id: Optional[str] = None,
    ) -> "object":
        from app.wishlist.domain.group import Group

        group = await self.groups.get(group_id)
        if not group:
            raise GroupNotFound("group not found")
        display_name = (display_name or "").strip()
        if not display_name:
            raise ValidationError("display_name is required")
        if len(display_name) > 100:
            raise ValidationError("display_name max length is 100")
        if len(group.members) >= MAX_MEMBERS:
            raise MembersCapExceeded(f"group may have at most {MAX_MEMBERS} members")

        member = Member.new(display_name=display_name, joined_via="quicklink")
        group.members.append(member)
        saved = await self.groups.save(group)
        await self.audit.record(
            group_id=group_id,
            action="member.add",
            actor_user_id=actor_user_id,
            actor_guest_id=actor_guest_id,
            metadata={"member_id": member.member_id, "display_name": display_name},
        )
        return saved


@dataclass
class LinkSelf:
    groups: GroupRepo
    audit: AuditSink

    async def __call__(
        self,
        *,
        group_id: str,
        user_id: str,
        username: str,
        member_id: Optional[str] = None,
    ):
        group = await self.groups.get(group_id)
        if not group:
            raise GroupNotFound("group not found")

        existing = group.find_linked_member_for_user(user_id)
        if existing:
            return group  # idempotent

        if member_id:
            target = group.find_member(member_id)
            if not target:
                raise MemberNotFound("member slot not found")
            if target.user_id is not None:
                raise ValidationError("member slot already linked")
            target.user_id = user_id
            target.joined_via = "login"
        else:
            if len(group.members) >= MAX_MEMBERS:
                raise MembersCapExceeded(f"group may have at most {MAX_MEMBERS} members")
            group.members.append(
                Member.new(display_name=username, user_id=user_id, joined_via="login")
            )

        saved = await self.groups.save(group)
        await self.audit.record(
            group_id=group_id,
            action="member.link",
            actor_user_id=user_id,
            metadata={"member_id": member_id},
        )
        return saved


@dataclass
class UnlinkMember:
    """
    Leader soft-unlinks a member slot (clears user_id, keeps display name).
    If the target is the leader, promote a successor first.
    Callers who want to leave themselves should use LeaveGroup.
    """

    groups: GroupRepo
    audit: AuditSink

    async def __call__(
        self,
        *,
        group_id: str,
        user_id: str,
        member_id: str,
    ):
        group = await self.groups.get(group_id)
        if not group:
            raise GroupNotFound("group not found")
        leader = group.find_linked_member_for_user(user_id)
        if not leader:
            raise NotLinkedMember("not a linked member")
        if not group.is_leader(leader.member_id):
            raise Forbidden("only the group leader can remove members")

        target = group.find_member(member_id)
        if not target:
            raise MemberNotFound("member slot not found")
        if target.member_id == leader.member_id:
            raise ValidationError("use leave to unlink yourself")

        was_leader_slot = group.is_leader(target.member_id)
        target.user_id = None

        if was_leader_slot:
            successor = group.pick_successor(excluding_member_id=None)
            if successor:
                group.leader_member_id = successor.member_id

        saved = await self.groups.save(group)
        await self.audit.record(
            group_id=group_id,
            action="member.unlink",
            actor_user_id=user_id,
            metadata={"member_id": member_id},
        )
        return saved


@dataclass
class RemoveMemberSlot:
    """
    Leader hard-removes a member slot (frees embedded capacity).
    Cascades delete of that member's products (and related purchase / active reservation).
    """

    groups: GroupRepo
    products: ProductRepo
    reservations: ReservationRepo
    purchases: PurchaseRepo
    audit: AuditSink

    async def __call__(
        self,
        *,
        group_id: str,
        user_id: str,
        member_id: str,
    ):
        group = await self.groups.get(group_id)
        if not group:
            raise GroupNotFound("group not found")
        leader = group.find_linked_member_for_user(user_id)
        if not leader:
            raise NotLinkedMember("not a linked member")
        if not group.is_leader(leader.member_id):
            raise Forbidden("only the group leader can remove members")

        target = group.find_member(member_id)
        if not target:
            raise MemberNotFound("member slot not found")
        if target.member_id == leader.member_id:
            raise ValidationError("use leave to remove yourself")

        was_leader_slot = group.is_leader(target.member_id)
        was_linked = bool(target.user_id)

        owned = await self.products.list_for_group(group_id, owner_member_id=member_id)
        for product in owned:
            pid = product.id or ""
            active = await self.reservations.get_active_for_product(pid)
            if active:
                active.status = ReservationStatus.RELEASED
                await self.reservations.save(active)
            await self.purchases.delete_for_product(pid)
            await self.products.delete(pid)

        group.members = [m for m in group.members if m.member_id != member_id]

        if was_leader_slot or group.leader_member_id == member_id:
            successor = group.pick_successor(excluding_member_id=None)
            if successor:
                group.leader_member_id = successor.member_id

        saved = await self.groups.save(group)
        await self.audit.record(
            group_id=group_id,
            action="member.remove",
            actor_user_id=user_id,
            metadata={
                "member_id": member_id,
                "products_deleted": len(owned),
                "was_linked": was_linked,
            },
        )
        return saved
