# FILE: ./app/models/trip.py (NEW FILE)
import uuid
from datetime import datetime
from beanie import Document, Link
from pydantic import BaseModel, Field
from typing import List, Optional
from pymongo import IndexModel
from app.models.user import User

class TripMember(BaseModel):
    member_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    display_name: str
    user: Optional[Link[User]] = None
    joined_via: str = Field(default="login")  # "login" | "quicklink"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Trip(Document):
    name: str = Field(..., max_length=100)
    description: Optional[str] = None
    members: List[TripMember] = []
    access_token: uuid.UUID = Field(default_factory=uuid.uuid4, unique=True)
    link_revoked: bool = Field(default=False)
    link_expires_at: Optional[datetime] = None
    access_token_version: int = Field(default=1)

    class Settings:
        name = "trips"
        indexes = [IndexModel("access_token", unique=True)]