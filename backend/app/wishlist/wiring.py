"""Compose adapters and use cases for Wishlist."""

from __future__ import annotations

from typing import Optional

from app.wishlist.adapters.clock import UtcClock
from app.wishlist.adapters.db.repositories import (
    BestEffortAuditSink,
    MongoGroupRepo,
    MongoProductRepo,
    MongoPurchaseRepo,
    MongoReservationRepo,
)
from app.wishlist.adapters.preview import build_preview_adapter
from app.wishlist.adapters.tokens import UuidTokenGen
from app.wishlist.application.groups import (
    CreateGroup,
    DeleteGroup,
    GetGroup,
    GetGroupByAccessToken,
    GetLink,
    LeaveGroup,
    ListMyGroups,
    RevokeLink,
    RotateLink,
    UpdateGroup,
)
from app.wishlist.application.members import AddMemberSlot, LinkSelf, RemoveMemberSlot, UnlinkMember
from app.wishlist.application.preview import PreviewProductUrl
from app.wishlist.application.products import AddProduct, DeleteProduct, UpdateProduct
from app.wishlist.application.reservations import (
    PurchaseReservation,
    ReleaseReservation,
    ReserveProduct,
)
from app.wishlist.application.views import ListProductsView


class Container:
    def __init__(self) -> None:
        clock = UtcClock()
        tokens = UuidTokenGen()
        preview = build_preview_adapter()
        audit = BestEffortAuditSink()

        groups = MongoGroupRepo()
        products = MongoProductRepo()
        reservations = MongoReservationRepo()
        purchases = MongoPurchaseRepo()

        self.clock = clock
        self.tokens = tokens
        self.preview = preview
        self.audit = audit
        self.groups = groups
        self.products = products
        self.reservations = reservations
        self.purchases = purchases

        self.create_group = CreateGroup(groups=groups, tokens=tokens, audit=audit)
        self.list_my_groups = ListMyGroups(groups=groups)
        self.get_group = GetGroup(groups=groups)
        self.get_group_by_access_token = GetGroupByAccessToken(groups=groups)
        self.update_group = UpdateGroup(groups=groups, audit=audit)
        self.delete_group = DeleteGroup(
            groups=groups,
            products=products,
            reservations=reservations,
            purchases=purchases,
            audit=audit,
        )
        self.leave_group = LeaveGroup(
            groups=groups,
            products=products,
            reservations=reservations,
            purchases=purchases,
            audit=audit,
        )
        self.rotate_link = RotateLink(
            groups=groups,
            products=products,
            reservations=reservations,
            tokens=tokens,
            audit=audit,
        )
        self.revoke_link = RevokeLink(groups=groups, audit=audit)
        self.get_link = GetLink(groups=groups)

        self.add_member_slot = AddMemberSlot(groups=groups, audit=audit)
        self.link_self = LinkSelf(groups=groups, audit=audit)
        self.unlink_member = UnlinkMember(groups=groups, audit=audit)
        self.remove_member_slot = RemoveMemberSlot(
            groups=groups,
            products=products,
            reservations=reservations,
            purchases=purchases,
            audit=audit,
        )

        self.add_product = AddProduct(groups=groups, products=products, audit=audit)
        self.update_product = UpdateProduct(groups=groups, products=products, audit=audit)
        self.delete_product = DeleteProduct(groups=groups, products=products, audit=audit)

        self.reserve_product = ReserveProduct(
            groups=groups,
            products=products,
            reservations=reservations,
            clock=clock,
            audit=audit,
        )
        self.release_reservation = ReleaseReservation(
            groups=groups,
            products=products,
            reservations=reservations,
            clock=clock,
            audit=audit,
        )
        self.purchase_reservation = PurchaseReservation(
            groups=groups,
            products=products,
            reservations=reservations,
            purchases=purchases,
            clock=clock,
            audit=audit,
        )
        self.list_products_view = ListProductsView(
            groups=groups, products=products, reservations=reservations
        )
        self.preview_product_url = PreviewProductUrl(groups=groups, preview=preview)


_container: Optional[Container] = None


def get_container() -> Container:
    global _container
    if _container is None:
        _container = Container()
    return _container


def reset_container() -> None:
    """Test helper."""
    global _container
    _container = None
