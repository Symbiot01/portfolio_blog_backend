"""HTTP dependencies: actor resolution and use-case factories."""

from __future__ import annotations

from typing import Optional, TypedDict

from fastapi import Depends, HTTPException, Request

from app.auth.core import current_optional_user
from app.models.user import User
from app.wishlist.domain.actor import GuestActor, MemberActor, WishlistActor
from app.wishlist.domain.errors import GroupNotFound, InvalidAccessToken, LinkRevoked
from app.wishlist.domain.group import Group
from app.wishlist.wiring import Container, get_container


class ActorContext(TypedDict):
    group: Group
    actor: WishlistActor
    guest_id_header: Optional[str]


def get_wishlist_container() -> Container:
    return get_container()


async def resolve_wishlist_actor(
    group_id: str,
    request: Request,
    user: Optional[User] = Depends(current_optional_user),
    container: Container = Depends(get_wishlist_container),
) -> ActorContext:
    group = await container.groups.get(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="group not found")

    guest_id_header = request.headers.get("X-Wishlist-Guest")

    if user is not None:
        linked = group.find_linked_member_for_user(str(user.id))
        if linked:
            return {
                "group": group,
                "actor": MemberActor(
                    user_id=str(user.id),
                    member_id=linked.member_id,
                    display_name=linked.display_name or user.username,
                ),
                "guest_id_header": guest_id_header,
            }

    if group.link_revoked:
        raise HTTPException(status_code=403, detail="access link revoked")

    access_token = request.headers.get("X-Wishlist-Access") or request.query_params.get(
        "access_token"
    )
    if not access_token:
        raise HTTPException(status_code=403, detail="not authorized for this group")

    if str(group.access_token) != str(access_token):
        raise HTTPException(status_code=403, detail="invalid access token for this group")

    return {
        "group": group,
        "actor": GuestActor(guest_id=guest_id_header),
        "guest_id_header": guest_id_header,
    }
