"""Product preview adapter — v1 always requires manual entry."""

from __future__ import annotations

from typing import Any, Dict

from app.wishlist.domain.errors import ValidationError


class NullPreview:
    async def from_url(self, url: str) -> Dict[str, Any]:
        raise ValidationError("URL preview unavailable; enter option details manually")
