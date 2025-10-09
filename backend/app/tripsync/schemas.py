# FILE: ./app/tripsync/schemas.py (NEW FILE)
from pydantic import BaseModel, Field
from beanie import PydanticObjectId
from typing import List, Optional
from datetime import datetime

# --- Trip Schemas ---
class TripCreate(BaseModel):
    name: str = Field(..., max_length=100)
    description: Optional[str] = None

class TripMemberInfo(BaseModel):
    member_id: str
    display_name: str
    linked: bool

class TripRead(BaseModel):
    id: PydanticObjectId
    name: str
    description: Optional[str]
    members: List[TripMemberInfo]
    secret_access_url: Optional[str] = None

# --- Member Schemas ---
class TripMemberCreate(BaseModel):
    display_name: str = Field(..., max_length=100)

class LinkSelfRequest(BaseModel):
    member_id: Optional[str] = None

# --- Itinerary Schemas ---
class ItineraryItemCreate(BaseModel):
    title: str = Field(..., max_length=100)
    item_type: str
    start_time: datetime
    end_time: Optional[datetime] = None
    location: Optional[str] = None

class ItineraryItemRead(ItineraryItemCreate):
    id: PydanticObjectId

# --- Expense Schemas ---
class ExpenseCreate(BaseModel):
    description: str = Field(..., max_length=150)
    amount: float
    paid_by_member_id: str
    split_with_member_ids: List[str]

class ExpenseRead(BaseModel):
    id: PydanticObjectId
    description: str
    amount: float
    paid_by_member_id: str
    split_with_member_ids: List[str]

class ItineraryItemUpdate(BaseModel):
    title: Optional[str] = None
    item_type: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    location: Optional[str] = None
    notes: Optional[str] = None

class ExpenseUpdate(BaseModel):
    description: Optional[str] = None
    amount: Optional[float] = None
    paid_by_member_id: Optional[str] = None
    split_with_member_ids: Optional[List[str]] = None

class SettlementCreate(BaseModel):
    payer_member_id: str
    payee_member_id: str
    amount: float

class SettlementRead(BaseModel):
    id: PydanticObjectId
    payer_member_id: str
    payee_member_id: str
    amount: float

class SettlementUpdate(BaseModel):
    payer_member_id: Optional[str] = None
    payee_member_id: Optional[str] = None
    amount: Optional[float] = None

class BalanceEntry(BaseModel):
    member_id: str
    balance: float  # positive means others owe them; negative means they owe

class LinkExpiryUpdate(BaseModel):
    link_expires_at: Optional[datetime] = None