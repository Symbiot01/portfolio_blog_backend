from beanie import Document, Link
from pydantic import Field
from datetime import datetime
from typing import Literal
from app.models.trip import Trip


class Settlement(Document):
    trip: Link[Trip]
    payer_member_id: str
    payee_member_id: str
    amount: float
    mode: Literal["cash", "upi", "card"] = Field(default="upi")
    createdAt: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "settlements"


