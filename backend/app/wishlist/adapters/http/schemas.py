"""Pydantic request/response schemas for Wishlist HTTP API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class GroupCreate(BaseModel):
    name: str = Field(..., max_length=100)
    description: Optional[str] = Field(default=None, max_length=2000)
    owners_can_see_fulfillment: bool
    max_active_reservations: int = Field(default=2, ge=1, le=5)


class GroupUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=100)
    description: Optional[str] = Field(default=None, max_length=2000)
    owners_can_see_fulfillment: Optional[bool] = None
    max_active_reservations: Optional[int] = Field(default=None, ge=1, le=5)


class MemberInfo(BaseModel):
    member_id: str
    display_name: str
    linked: bool
    is_leader: bool = False
    is_you: bool = False


class GroupSettingsRead(BaseModel):
    owners_can_see_fulfillment: bool
    max_active_reservations: int


class GroupRead(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    members: List[MemberInfo]
    settings: GroupSettingsRead
    leader_member_id: str
    link_revoked: bool = False
    secret_access_url: Optional[str] = None
    member_cap: int = 20


class MemberCreate(BaseModel):
    display_name: str = Field(..., max_length=100)


class LinkSelfRequest(BaseModel):
    member_id: Optional[str] = None


class ProductOptionIn(BaseModel):
    title: str = Field(..., max_length=150)
    url: Optional[str] = Field(default=None, max_length=2000)
    notes: Optional[str] = Field(default=None, max_length=2000)
    price: Optional[float] = None
    currency: Optional[str] = Field(default=None, max_length=8)
    image_url: Optional[str] = Field(default=None, max_length=2000)


class ProductCreate(BaseModel):
    title: str = Field(..., max_length=150)
    description: Optional[str] = Field(default=None, max_length=2000)
    options: List[ProductOptionIn] = Field(..., min_length=1, max_length=20)


class ProductUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=150)
    description: Optional[str] = Field(default=None, max_length=2000)
    options: Optional[List[ProductOptionIn]] = Field(default=None, max_length=20)


class ProductOptionOut(BaseModel):
    option_id: str
    title: str
    url: Optional[str] = None
    notes: Optional[str] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    image_url: Optional[str] = None


class ReservationInfo(BaseModel):
    reservation_id: Optional[str] = None
    reserved_as_name: Optional[str] = None
    expires_at: Optional[str] = None


class ProductRead(BaseModel):
    id: str
    group_id: str
    owner_member_id: str
    title: str
    description: Optional[str] = None
    options: List[ProductOptionOut]
    status: str
    created_by_actor_key: str
    reservation: Optional[ReservationInfo] = None


class ReserveRequest(BaseModel):
    reserved_as_name: Optional[str] = Field(default=None, max_length=100)


class ReserveResponse(BaseModel):
    reservation_id: str
    guest_id: Optional[str] = None
    expires_at: datetime
    reserved_as_name: str


class PurchaseRequest(BaseModel):
    option_id: Optional[str] = None


class PurchaseResponse(BaseModel):
    purchase_id: str
    product_id: str
    reservation_id: str
    bought_at: datetime


class LinkInfo(BaseModel):
    secret_access_url: str
    link_revoked: bool
    access_token: UUID


class UrlPreviewIn(BaseModel):
    url: str = Field(..., max_length=2000)


class UrlPreviewOut(BaseModel):
    title: Optional[str] = None
    url: str
    price: Optional[float] = None
    currency: Optional[str] = None
    image_url: Optional[str] = None
    notes: Optional[str] = None
    source: Optional[str] = None
