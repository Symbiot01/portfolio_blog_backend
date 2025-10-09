# FILE: ./app/models/itinerary.py
from beanie import Document, Link, PydanticObjectId
from pydantic import Field
from typing import Optional
from datetime import datetime
from app.models.trip import Trip

class ItineraryItem(Document):
    trip: Link[Trip]
    title: str = Field(..., max_length=100)
    item_type: str # e.g., "Flight", "Hotel", "Activity"
    start_time: datetime
    end_time: Optional[datetime] = None
    location: Optional[str] = None
    notes: Optional[str] = None

    class Settings:
        name = "itinerary_items"