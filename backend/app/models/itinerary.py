# FILE: ./app/models/itinerary.py
from beanie import Document, Link
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

    # Optional day-based organization (UI-friendly; does not replace start_time sorting)
    day_index: Optional[int] = Field(default=None, ge=1)
    all_day: bool = Field(default=False)

    # Optional place metadata for mapping
    place_id: Optional[str] = Field(default=None, max_length=200)
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lng: Optional[float] = Field(default=None, ge=-180, le=180)

    class Settings:
        name = "itinerary_items"