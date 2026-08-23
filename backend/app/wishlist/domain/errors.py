"""Domain exceptions for Wishlist. Mapped to HTTP in the router adapter."""

from __future__ import annotations


class WishlistError(Exception):
    """Base class for all Wishlist domain errors."""

    code: str = "wishlist_error"

    def __init__(self, message: str = "") -> None:
        self.message = message or self.code
        super().__init__(self.message)


class GroupNotFound(WishlistError):
    code = "group_not_found"


class ProductNotFound(WishlistError):
    code = "product_not_found"


class ReservationNotFound(WishlistError):
    code = "reservation_not_found"


class MemberNotFound(WishlistError):
    code = "member_not_found"


class InvalidAccessToken(WishlistError):
    code = "invalid_access_token"


class LinkRevoked(WishlistError):
    code = "link_revoked"


class NotLinkedMember(WishlistError):
    code = "not_linked_member"


class NotReservationOwner(WishlistError):
    code = "not_reservation_owner"


class LoginRequiredForPurchase(WishlistError):
    code = "login_required_for_purchase"


class CannotReserveOwnList(WishlistError):
    code = "cannot_reserve_own_list"


class ValidationError(WishlistError):
    code = "validation_error"


class AlreadyReserved(WishlistError):
    code = "already_reserved"


class ReservationCapExceeded(WishlistError):
    code = "reservation_cap_exceeded"


class ProductNotPurchasable(WishlistError):
    code = "product_not_purchasable"


class MembersCapExceeded(WishlistError):
    code = "members_cap_exceeded"


class ProductFrozen(WishlistError):
    code = "product_frozen"


class Forbidden(WishlistError):
    code = "forbidden"
