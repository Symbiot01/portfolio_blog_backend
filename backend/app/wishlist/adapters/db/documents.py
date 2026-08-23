"""Beanie documents for Wishlist. Indexes declared in Settings."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID, uuid4

from beanie import Document, Link
from pydantic import BaseModel, Field
from pymongo import ASCENDING, IndexModel

from app.models.user import User


class GroupSettingsDoc(BaseModel):
    owners_can_see_fulfillment: bool
    max_active_reservations: int = Field(default=2, ge=1, le=5)


class MemberDoc(BaseModel):
    member_id: str
    display_name: str = Field(..., max_length=100)
    user: Optional[Link[User]] = None
    joined_via: Literal["login", "quicklink"] = "login"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ProductOptionDoc(BaseModel):
    option_id: str
    title: str = Field(..., max_length=150)
    url: Optional[str] = Field(default=None, max_length=2000)
    notes: Optional[str] = Field(default=None, max_length=2000)
    price: Optional[float] = None
    currency: Optional[str] = Field(default=None, max_length=8)
    image_url: Optional[str] = Field(default=None, max_length=2000)


class WishlistGroupDoc(Document):
    name: str = Field(..., max_length=100)
    description: Optional[str] = Field(default=None, max_length=2000)
    access_token: UUID = Field(default_factory=uuid4)
    link_revoked: bool = False
    leader_member_id: str
    settings: GroupSettingsDoc
    members: List[MemberDoc] = Field(default_factory=list)

    class Settings:
        name = "wishlist_groups"
        indexes = [
            IndexModel([("access_token", ASCENDING)], unique=True),
            IndexModel([("members.user.$id", ASCENDING)]),
        ]


class WishlistProductDoc(Document):
    group_id: str = Field(..., max_length=64)
    owner_member_id: str = Field(..., max_length=64)
    title: str = Field(..., max_length=150)
    description: Optional[str] = Field(default=None, max_length=2000)
    options: List[ProductOptionDoc] = Field(default_factory=list)
    status: Literal["open", "reserved", "bought"] = "open"
    created_by_actor_key: str = Field(..., max_length=128)

    class Settings:
        name = "wishlist_products"
        indexes = [
            IndexModel([("group_id", ASCENDING), ("owner_member_id", ASCENDING)]),
        ]


class WishlistReservationDoc(Document):
    product_id: str = Field(..., max_length=64)
    group_id: str = Field(..., max_length=64)
    status: Literal["active", "released", "expired", "purchased"] = "active"
    expires_at: datetime
    reserved_as_name: str = Field(..., max_length=100)
    actor_user_id: Optional[str] = Field(default=None, max_length=64)
    guest_id: Optional[str] = Field(default=None, max_length=128)

    class Settings:
        name = "wishlist_reservations"
        indexes = [
            IndexModel(
                [("product_id", ASCENDING)],
                unique=True,
                partialFilterExpression={"status": "active"},
            ),
            IndexModel(
                [("group_id", ASCENDING), ("actor_user_id", ASCENDING), ("status", ASCENDING)]
            ),
            IndexModel(
                [("group_id", ASCENDING), ("guest_id", ASCENDING), ("status", ASCENDING)]
            ),
            IndexModel([("expires_at", ASCENDING), ("status", ASCENDING)]),
        ]


class WishlistPurchaseDoc(Document):
    reservation_id: str = Field(..., max_length=64)
    product_id: str = Field(..., max_length=64)
    group_id: str = Field(..., max_length=64)
    buyer_user_id: str = Field(..., max_length=64)
    bought_at: datetime = Field(default_factory=datetime.utcnow)
    option_id: Optional[str] = Field(default=None, max_length=64)

    class Settings:
        name = "wishlist_purchases"
        indexes = [
            IndexModel([("group_id", ASCENDING)]),
            IndexModel([("product_id", ASCENDING)]),
        ]


class WishlistAuditEventDoc(Document):
    ts: datetime = Field(default_factory=datetime.utcnow)
    group_id: str = Field(..., max_length=64)
    action: str = Field(..., max_length=80)
    actor_user_id: Optional[str] = Field(default=None, max_length=64)
    actor_guest_id: Optional[str] = Field(default=None, max_length=128)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Settings:
        name = "wishlist_audit_events"


WISHLIST_DOCUMENT_MODELS = [
    WishlistGroupDoc,
    WishlistProductDoc,
    WishlistReservationDoc,
    WishlistPurchaseDoc,
    WishlistAuditEventDoc,
]
