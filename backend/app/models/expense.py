# FILE: ./app/models/expense.py 
from beanie import Document, Link
from pydantic import Field, BaseModel
from typing import List, Literal, Optional
from datetime import datetime
from app.models.trip import Trip


class CustomSplit(BaseModel):
    member_id: str
    amount: float


class Expense(Document):
    trip: Link[Trip]
    description: str = Field(..., max_length=150)
    amount: float
    paid_by_member_id: str  # TripMember.member_id of payer
    split_with_member_ids: List[str] = []  # TripMember.member_id list
    split_type: Literal["equal", "exact"] = "equal"
    custom_splits: List[dict] = []  # Store as dictionaries
    createdAt: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "expenses"