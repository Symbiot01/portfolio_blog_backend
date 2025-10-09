# FILE: ./app/models/expense.py 
from beanie import Document, Link
from pydantic import Field
from typing import List
from datetime import datetime
from app.models.trip import Trip


class Expense(Document):
    trip: Link[Trip]
    description: str = Field(..., max_length=150)
    amount: float
    paid_by_member_id: str  # TripMember.member_id of payer
    split_with_member_ids: List[str] = []  # TripMember.member_id list
    createdAt: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "expenses"