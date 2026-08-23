"""Wishlist HTTP router."""

from __future__ import annotations

import secrets
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.auth.core import current_active_user
from app.models.user import User
from app.wishlist.adapters.http.deps import (
    ActorContext,
    get_wishlist_container,
    resolve_wishlist_actor,
)
from app.wishlist.adapters.http.schemas import (
    GroupCreate,
    GroupRead,
    GroupSettingsRead,
    GroupUpdate,
    LinkInfo,
    LinkSelfRequest,
    MemberCreate,
    MemberInfo,
    ProductCreate,
    ProductRead,
    ProductUpdate,
    PurchaseRequest,
    PurchaseResponse,
    ReserveRequest,
    ReserveResponse,
    UrlPreviewIn,
    UrlPreviewOut,
)
from app.wishlist.domain.actor import GuestActor, MemberActor, WishlistActor
from app.wishlist.domain.errors import (
    AlreadyReserved,
    CannotReserveOwnList,
    Forbidden,
    GroupNotFound,
    InvalidAccessToken,
    LinkRevoked,
    LoginRequiredForPurchase,
    MemberNotFound,
    MembersCapExceeded,
    NotLinkedMember,
    NotReservationOwner,
    ProductFrozen,
    ProductNotFound,
    ProductNotPurchasable,
    ReservationCapExceeded,
    ReservationNotFound,
    ValidationError,
    WishlistError,
)
from app.wishlist.domain.group import MAX_MEMBERS, Group
from app.wishlist.wiring import Container

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

_ERROR_STATUS = {
    GroupNotFound: 404,
    ProductNotFound: 404,
    ReservationNotFound: 404,
    MemberNotFound: 404,
    InvalidAccessToken: 403,
    LinkRevoked: 403,
    NotLinkedMember: 403,
    NotReservationOwner: 403,
    Forbidden: 403,
    LoginRequiredForPurchase: 401,
    CannotReserveOwnList: 400,
    ValidationError: 400,
    ProductFrozen: 409,
    AlreadyReserved: 409,
    ReservationCapExceeded: 409,
    ProductNotPurchasable: 409,
    MembersCapExceeded: 409,
}


def _http_from_domain(exc: WishlistError) -> HTTPException:
    status = 400
    for cls, code in _ERROR_STATUS.items():
        if isinstance(exc, cls):
            status = code
            break
    return HTTPException(status_code=status, detail=exc.message)


def _ensure_guest_actor(actor: WishlistActor) -> Tuple[WishlistActor, Optional[str]]:
    """
    Share-link guests need a stable guest_id for create/edit attribution.
    Mint one when the client has not sent X-Wishlist-Guest yet.
    """
    if not isinstance(actor, GuestActor):
        return actor, None
    if actor.guest_id:
        return actor, None
    issued = secrets.token_urlsafe(32)
    return GuestActor(guest_id=issued, display_name=actor.display_name), issued


def _group_to_read(
    group: Group,
    *,
    request: Optional[Request] = None,
    include_secret: bool = False,
    viewer_user_id: Optional[str] = None,
) -> GroupRead:
    secret = None
    if include_secret and request is not None:
        base = str(request.base_url)
        secret = f"{base}api/wishlist/access/{group.access_token}"
    return GroupRead(
        id=group.id or "",
        name=group.name,
        description=group.description,
        members=[
            MemberInfo(
                member_id=m.member_id,
                display_name=m.display_name,
                linked=bool(m.user_id),
                is_leader=m.member_id == group.leader_member_id,
                is_you=bool(viewer_user_id and m.user_id == viewer_user_id),
            )
            for m in group.members
        ],
        settings=GroupSettingsRead(
            owners_can_see_fulfillment=group.settings.owners_can_see_fulfillment,
            max_active_reservations=group.settings.max_active_reservations,
        ),
        leader_member_id=group.leader_member_id,
        link_revoked=group.link_revoked,
        secret_access_url=secret,
        member_cap=MAX_MEMBERS,
    )


# --- Static paths first ---


@router.post("/", response_model=GroupRead, status_code=201)
async def create_group(
    payload: GroupCreate,
    request: Request,
    user: User = Depends(current_active_user),
    container: Container = Depends(get_wishlist_container),
):
    try:
        group = await container.create_group(
            user_id=str(user.id),
            username=user.username,
            name=payload.name,
            description=payload.description,
            owners_can_see_fulfillment=payload.owners_can_see_fulfillment,
            max_active_reservations=payload.max_active_reservations,
        )
    except WishlistError as e:
        raise _http_from_domain(e)
    return _group_to_read(group, request=request, include_secret=True, viewer_user_id=str(user.id))


@router.get("/my", response_model=List[GroupRead])
async def list_my_groups(
    user: User = Depends(current_active_user),
    container: Container = Depends(get_wishlist_container),
):
    groups = await container.list_my_groups(user_id=str(user.id))
    return [_group_to_read(g) for g in groups]


@router.get("/access/{access_token}", response_model=GroupRead)
@limiter.limit("30/minute")
async def preview_by_access(
    access_token: str,
    request: Request,
    container: Container = Depends(get_wishlist_container),
):
    try:
        group = await container.get_group_by_access_token(access_token=access_token)
    except WishlistError as e:
        raise _http_from_domain(e)
    return _group_to_read(group, include_secret=False)


# --- Member / link routes (before generic GET /{group_id} is fine; FastAPI matches by path) ---


@router.post("/{group_id}/members", response_model=GroupRead)
@limiter.limit("60/minute")
async def add_member(
    group_id: str,
    payload: MemberCreate,
    request: Request,
    ctx: ActorContext = Depends(resolve_wishlist_actor),
    container: Container = Depends(get_wishlist_container),
):
    actor = ctx["actor"]
    try:
        group = await container.add_member_slot(
            group_id=group_id,
            display_name=payload.display_name,
            actor_user_id=getattr(actor, "user_id", None),
            actor_guest_id=getattr(actor, "guest_id", None),
        )
    except WishlistError as e:
        raise _http_from_domain(e)
    return _group_to_read(group)


@router.post("/{group_id}/members/link-self", response_model=GroupRead)
async def link_self(
    group_id: str,
    payload: LinkSelfRequest,
    user: User = Depends(current_active_user),
    container: Container = Depends(get_wishlist_container),
):
    try:
        group = await container.link_self(
            group_id=group_id,
            user_id=str(user.id),
            username=user.username,
            member_id=payload.member_id,
        )
    except WishlistError as e:
        raise _http_from_domain(e)
    return _group_to_read(group)


@router.post("/{group_id}/leave", status_code=204)
async def leave_group(
    group_id: str,
    user: User = Depends(current_active_user),
    container: Container = Depends(get_wishlist_container),
):
    try:
        await container.leave_group(group_id=group_id, user_id=str(user.id))
    except WishlistError as e:
        raise _http_from_domain(e)
    return Response(status_code=204)


@router.post("/{group_id}/members/{member_id}/unlink", response_model=GroupRead)
@limiter.limit("30/minute")
async def unlink_member(
    group_id: str,
    member_id: str,
    request: Request,
    user: User = Depends(current_active_user),
    container: Container = Depends(get_wishlist_container),
):
    try:
        group = await container.unlink_member(
            group_id=group_id, user_id=str(user.id), member_id=member_id
        )
    except WishlistError as e:
        raise _http_from_domain(e)
    return _group_to_read(group, viewer_user_id=str(user.id))


@router.delete("/{group_id}/members/{member_id}", response_model=GroupRead)
@limiter.limit("30/minute")
async def remove_member_slot(
    group_id: str,
    member_id: str,
    request: Request,
    user: User = Depends(current_active_user),
    container: Container = Depends(get_wishlist_container),
):
    """Hard-remove a member slot (frees the 20-member embedded cap). Leader only."""
    try:
        group = await container.remove_member_slot(
            group_id=group_id, user_id=str(user.id), member_id=member_id
        )
    except WishlistError as e:
        raise _http_from_domain(e)
    return _group_to_read(group, viewer_user_id=str(user.id))


@router.patch("/{group_id}", response_model=GroupRead)
@limiter.limit("30/minute")
async def update_group(
    group_id: str,
    payload: GroupUpdate,
    request: Request,
    user: User = Depends(current_active_user),
    container: Container = Depends(get_wishlist_container),
):
    from app.wishlist.application.groups import _UNSET

    fields_set = payload.model_fields_set
    try:
        group = await container.update_group(
            group_id=group_id,
            user_id=str(user.id),
            name=payload.name,
            description=payload.description if "description" in fields_set else _UNSET,
            owners_can_see_fulfillment=payload.owners_can_see_fulfillment,
            max_active_reservations=payload.max_active_reservations,
        )
    except WishlistError as e:
        raise _http_from_domain(e)
    return _group_to_read(group, viewer_user_id=str(user.id))


@router.delete("/{group_id}", status_code=204)
@limiter.limit("10/minute")
async def delete_group(
    group_id: str,
    request: Request,
    user: User = Depends(current_active_user),
    container: Container = Depends(get_wishlist_container),
):
    try:
        await container.delete_group(group_id=group_id, user_id=str(user.id))
    except WishlistError as e:
        raise _http_from_domain(e)
    return Response(status_code=204)


@router.get("/{group_id}/link", response_model=LinkInfo)
async def get_link(
    group_id: str,
    request: Request,
    user: User = Depends(current_active_user),
    container: Container = Depends(get_wishlist_container),
):
    try:
        group = await container.get_link(group_id=group_id, user_id=str(user.id))
    except WishlistError as e:
        raise _http_from_domain(e)
    base = str(request.base_url)
    return LinkInfo(
        secret_access_url=f"{base}api/wishlist/access/{group.access_token}",
        link_revoked=group.link_revoked,
        access_token=group.access_token,
    )


@router.post("/{group_id}/rotate-link", response_model=LinkInfo)
@limiter.limit("20/minute")
async def rotate_link(
    group_id: str,
    request: Request,
    user: User = Depends(current_active_user),
    container: Container = Depends(get_wishlist_container),
):
    try:
        group = await container.rotate_link(group_id=group_id, user_id=str(user.id))
    except WishlistError as e:
        raise _http_from_domain(e)
    base = str(request.base_url)
    return LinkInfo(
        secret_access_url=f"{base}api/wishlist/access/{group.access_token}",
        link_revoked=group.link_revoked,
        access_token=group.access_token,
    )


@router.post("/{group_id}/revoke-link", status_code=204)
@limiter.limit("20/minute")
async def revoke_link(
    group_id: str,
    request: Request,
    user: User = Depends(current_active_user),
    container: Container = Depends(get_wishlist_container),
):
    try:
        await container.revoke_link(group_id=group_id, user_id=str(user.id))
    except WishlistError as e:
        raise _http_from_domain(e)
    return Response(status_code=204)


@router.post("/{group_id}/preview-url", response_model=UrlPreviewOut)
@limiter.limit("10/minute")
async def preview_product_url(
    group_id: str,
    payload: UrlPreviewIn,
    request: Request,
    ctx: ActorContext = Depends(resolve_wishlist_actor),
    container: Container = Depends(get_wishlist_container),
):
    """
    Extract draft store-option fields (title, image, price) from a public product URL.
    Does not persist anything — client confirms via create/update product.
    """
    try:
        draft = await container.preview_product_url(group_id=group_id, url=payload.url)
    except WishlistError as e:
        raise _http_from_domain(e)
    return UrlPreviewOut(**draft)


# --- Products ---


@router.post(
    "/{group_id}/members/{member_id}/products",
    response_model=ProductRead,
    status_code=201,
)
@limiter.limit("60/minute")
async def add_product(
    group_id: str,
    member_id: str,
    payload: ProductCreate,
    request: Request,
    ctx: ActorContext = Depends(resolve_wishlist_actor),
    container: Container = Depends(get_wishlist_container),
):
    actor, issued_guest = _ensure_guest_actor(ctx["actor"])
    try:
        product = await container.add_product(
            group_id=group_id,
            owner_member_id=member_id,
            title=payload.title,
            description=payload.description,
            options=[o.model_dump() for o in payload.options],
            actor=actor,
        )
    except WishlistError as e:
        raise _http_from_domain(e)
    return ProductRead(
        id=product.id or "",
        group_id=product.group_id,
        owner_member_id=product.owner_member_id,
        title=product.title,
        description=product.description,
        options=[
            {
                "option_id": o.option_id,
                "title": o.title,
                "url": o.url,
                "notes": o.notes,
                "price": o.price,
                "currency": o.currency,
                "image_url": o.image_url,
            }
            for o in product.options
        ],
        status=product.status.value,
        created_by_actor_key=product.created_by_actor_key,
        guest_id=issued_guest
        or (actor.guest_id if isinstance(actor, GuestActor) else None),
    )


@router.get("/{group_id}/products", response_model=List[ProductRead])
async def list_products(
    group_id: str,
    owner_member_id: Optional[str] = None,
    ctx: ActorContext = Depends(resolve_wishlist_actor),
    container: Container = Depends(get_wishlist_container),
):
    try:
        items = await container.list_products_view(
            group_id=group_id,
            viewer=ctx["actor"],
            owner_member_id=owner_member_id,
        )
    except WishlistError as e:
        raise _http_from_domain(e)
    return [ProductRead(**item) for item in items]


@router.patch("/{group_id}/products/{product_id}", response_model=ProductRead)
@limiter.limit("60/minute")
async def update_product(
    group_id: str,
    product_id: str,
    payload: ProductUpdate,
    request: Request,
    ctx: ActorContext = Depends(resolve_wishlist_actor),
    container: Container = Depends(get_wishlist_container),
):
    try:
        product = await container.update_product(
            group_id=group_id,
            product_id=product_id,
            actor=ctx["actor"],
            title=payload.title,
            description=payload.description,
            options=[o.model_dump() for o in payload.options]
            if payload.options is not None
            else None,
        )
    except WishlistError as e:
        raise _http_from_domain(e)
    return ProductRead(
        id=product.id or "",
        group_id=product.group_id,
        owner_member_id=product.owner_member_id,
        title=product.title,
        description=product.description,
        options=[
            {
                "option_id": o.option_id,
                "title": o.title,
                "url": o.url,
                "notes": o.notes,
                "price": o.price,
                "currency": o.currency,
                "image_url": o.image_url,
            }
            for o in product.options
        ],
        status=product.status.value,
        created_by_actor_key=product.created_by_actor_key,
    )


@router.delete("/{group_id}/products/{product_id}", status_code=204)
@limiter.limit("60/minute")
async def delete_product(
    group_id: str,
    product_id: str,
    request: Request,
    ctx: ActorContext = Depends(resolve_wishlist_actor),
    container: Container = Depends(get_wishlist_container),
):
    try:
        await container.delete_product(
            group_id=group_id, product_id=product_id, actor=ctx["actor"]
        )
    except WishlistError as e:
        raise _http_from_domain(e)
    return Response(status_code=204)


# --- Reserve / release / purchase ---


@router.post(
    "/{group_id}/products/{product_id}/reserve",
    response_model=ReserveResponse,
    status_code=201,
)
@limiter.limit("60/minute")
async def reserve_product(
    group_id: str,
    product_id: str,
    payload: ReserveRequest,
    request: Request,
    ctx: ActorContext = Depends(resolve_wishlist_actor),
    container: Container = Depends(get_wishlist_container),
):
    try:
        reservation, issued_guest = await container.reserve_product(
            group_id=group_id,
            product_id=product_id,
            actor=ctx["actor"],
            reserved_as_name=payload.reserved_as_name,
            guest_id_header=ctx.get("guest_id_header"),
        )
    except WishlistError as e:
        raise _http_from_domain(e)
    return ReserveResponse(
        reservation_id=reservation.id or "",
        guest_id=issued_guest or reservation.guest_id,
        expires_at=reservation.expires_at,
        reserved_as_name=reservation.reserved_as_name,
    )


@router.post("/{group_id}/reservations/{reservation_id}/release", status_code=204)
@limiter.limit("60/minute")
async def release_reservation(
    group_id: str,
    reservation_id: str,
    request: Request,
    ctx: ActorContext = Depends(resolve_wishlist_actor),
    container: Container = Depends(get_wishlist_container),
):
    try:
        await container.release_reservation(
            group_id=group_id,
            reservation_id=reservation_id,
            actor=ctx["actor"],
            guest_id_header=ctx.get("guest_id_header"),
        )
    except WishlistError as e:
        raise _http_from_domain(e)
    return Response(status_code=204)


@router.post(
    "/{group_id}/reservations/{reservation_id}/purchase",
    response_model=PurchaseResponse,
)
@limiter.limit("60/minute")
async def purchase_reservation(
    group_id: str,
    reservation_id: str,
    request: Request,
    payload: PurchaseRequest = PurchaseRequest(),
    user: User = Depends(current_active_user),
    container: Container = Depends(get_wishlist_container),
):
    guest_id = request.headers.get("X-Wishlist-Guest")
    # Purchase requires JWT; still verify the caller can access the group
    # (linked member OR share token). Linked members skip token.
    group = await container.groups.get(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="group not found")
    linked = group.find_linked_member_for_user(str(user.id))
    if not linked:
        if group.link_revoked:
            raise HTTPException(status_code=403, detail="access link revoked")
        access_token = request.headers.get("X-Wishlist-Access") or request.query_params.get(
            "access_token"
        )
        if not access_token or str(group.access_token) != str(access_token):
            raise HTTPException(status_code=403, detail="not authorized for this group")

    try:
        purchase = await container.purchase_reservation(
            group_id=group_id,
            reservation_id=reservation_id,
            user_id=str(user.id),
            guest_id_header=guest_id,
            option_id=payload.option_id,
        )
    except WishlistError as e:
        raise _http_from_domain(e)
    return PurchaseResponse(
        purchase_id=purchase.id or "",
        product_id=purchase.product_id,
        reservation_id=purchase.reservation_id,
        bought_at=purchase.bought_at,
    )


@router.get("/{group_id}", response_model=GroupRead)
async def get_group(
    group_id: str,
    ctx: ActorContext = Depends(resolve_wishlist_actor),
):
    viewer = None
    actor = ctx["actor"]
    if isinstance(actor, MemberActor):
        viewer = actor.user_id
    return _group_to_read(ctx["group"], viewer_user_id=viewer)
