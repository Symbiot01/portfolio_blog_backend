"""URL preview use case."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from app.wishlist.application.ports import GroupRepo, ProductPreview
from app.wishlist.domain.errors import GroupNotFound, ValidationError


@dataclass
class PreviewProductUrl:
    groups: GroupRepo
    preview: ProductPreview

    async def __call__(self, *, group_id: str, url: str) -> Dict[str, Any]:
        group = await self.groups.get(group_id)
        if not group:
            raise GroupNotFound("group not found")
        url = (url or "").strip()
        if not url:
            raise ValidationError("url is required")
        return await self.preview.from_url(url)
