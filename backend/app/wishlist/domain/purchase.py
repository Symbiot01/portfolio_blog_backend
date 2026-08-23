"""Purchase domain entity."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Purchase:
    id: Optional[str]
    reservation_id: str
    product_id: str
    buyer_user_id: str
    bought_at: datetime = field(default_factory=datetime.utcnow)
    option_id: Optional[str] = None
