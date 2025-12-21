from __future__ import annotations

from datetime import datetime, date
from typing import List, Optional

from beanie import Document, Link
from pydantic import BaseModel, Field

from app.models.trip import Trip


class TripDateRange(BaseModel):
    start: Optional[date] = None
    end: Optional[date] = None


class TravelPoint(BaseModel):
    date: date
    city: Optional[str] = Field(default=None, max_length=120)
    notes: Optional[str] = Field(default=None, max_length=500)


class LodgingStay(BaseModel):
    lodging_id: str = Field(..., max_length=64)
    from_night: date
    to_night_exclusive: date
    notes: Optional[str] = Field(default=None, max_length=500)


class MemberTravelSegment(BaseModel):
    arrival: TravelPoint
    departure: TravelPoint
    lodging_stay: Optional[LodgingStay] = None


class TripMemberDoc(BaseModel):
    member_id: str = Field(..., max_length=64)
    display_name: str = Field(..., max_length=100)
    travel_segments: List[MemberTravelSegment] = Field(default_factory=list)
    notes: Optional[str] = Field(default=None, max_length=1000)


class BookingNights(BaseModel):
    check_in_date: date
    check_out_date: date
    nights: int = Field(..., ge=1)
    check_in_time_note: Optional[str] = Field(default=None, max_length=80)
    check_out_time_note: Optional[str] = Field(default=None, max_length=80)


class LodgingDoc(BaseModel):
    lodging_id: str = Field(..., max_length=64)
    name: str = Field(..., max_length=150)
    city: Optional[str] = Field(default=None, max_length=120)
    address: Optional[str] = Field(default=None, max_length=250)
    booking_nights: BookingNights
    rooms: Optional[int] = Field(default=None, ge=1, le=50)
    confirmation_code: Optional[str] = Field(default=None, max_length=80)
    contact_phone: Optional[str] = Field(default=None, max_length=40)
    notes: Optional[str] = Field(default=None, max_length=1000)


class TripDoc(Document):
    """
    Per-trip editable document:
    - human-friendly natural language brief
    - structured member travel segments
    - lodging bookings stored by nights (date-only)
    """

    schema_version: int = Field(default=2, ge=1)
    trip: Link[Trip]

    timezone: str = Field(default="UTC", max_length=64)
    title: str = Field(default="", max_length=150)
    date_range: TripDateRange = Field(default_factory=TripDateRange)

    members: List[TripMemberDoc] = Field(default_factory=list)
    lodgings: List[LodgingDoc] = Field(default_factory=list)

    natural_language_trip_brief: str = Field(default="", max_length=20000)
    shared_notes: str = Field(default="", max_length=20000)

    revision: int = Field(default=1, ge=1)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "trip_docs"


