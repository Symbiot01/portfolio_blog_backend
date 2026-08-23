"""Product and option domain entities with strict lifecycle freeze rules."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional
from uuid import uuid4

from app.wishlist.domain.errors import ProductFrozen, ValidationError


class ProductStatus(str, Enum):
    OPEN = "open"
    RESERVED = "reserved"
    BOUGHT = "bought"


MAX_OPTIONS = 20


@dataclass
class ProductOption:
    option_id: str
    title: str
    url: Optional[str] = None
    notes: Optional[str] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    image_url: Optional[str] = None

    @classmethod
    def new(
        cls,
        title: str,
        *,
        url: Optional[str] = None,
        notes: Optional[str] = None,
        price: Optional[float] = None,
        currency: Optional[str] = None,
        image_url: Optional[str] = None,
    ) -> "ProductOption":
        if not title or not title.strip():
            raise ValidationError("option title is required")
        return cls(
            option_id=uuid4().hex,
            title=title.strip(),
            url=url,
            notes=notes,
            price=price,
            currency=currency,
            image_url=image_url,
        )


@dataclass
class Product:
    id: Optional[str]
    group_id: str
    owner_member_id: str
    title: str
    description: Optional[str]
    options: List[ProductOption]
    status: ProductStatus
    created_by_actor_key: str

    def assert_can_patch(self) -> None:
        if self.status != ProductStatus.OPEN:
            raise ProductFrozen("product can only be updated while open")

    def assert_can_delete(self, *, is_leader: bool, is_creator: bool) -> None:
        if self.status == ProductStatus.RESERVED:
            raise ProductFrozen("cannot delete a reserved product; release or wait for TTL first")
        if self.status == ProductStatus.BOUGHT:
            if not is_leader:
                raise ProductFrozen("only the leader can delete a bought product")
            return
        # open
        if not (is_leader or is_creator):
            raise ProductFrozen("only creator or leader can delete an open product")

    @staticmethod
    def validate_options(options: List[ProductOption]) -> None:
        if not options:
            raise ValidationError("at least one option is required")
        if len(options) > MAX_OPTIONS:
            raise ValidationError(f"at most {MAX_OPTIONS} options allowed")
