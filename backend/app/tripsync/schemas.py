# FILE: ./app/tripsync/schemas.py (NEW FILE)
from pydantic import BaseModel, Field
from beanie import PydanticObjectId
from typing import Any, Dict, List, Optional, Literal
from datetime import datetime, date

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
    notes: Optional[str] = Field(default=None, max_length=2000)
    day_index: Optional[int] = Field(default=None, ge=1)
    all_day: bool = False
    place_id: Optional[str] = Field(default=None, max_length=200)
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lng: Optional[float] = Field(default=None, ge=-180, le=180)

class ItineraryItemRead(ItineraryItemCreate):
    id: PydanticObjectId

# --- Expense Schemas ---
class CustomSplit(BaseModel):
    member_id: str
    amount: float

class ExpenseCreate(BaseModel):
    description: str = Field(..., max_length=150)
    amount: float
    paid_by_member_id: str
    split_with_member_ids: Optional[List[str]] = Field(default_factory=list)
    split_type: Literal["equal", "exact"] = "equal"
    custom_splits: Optional[List[CustomSplit]] = Field(default_factory=list)

class ExpenseRead(BaseModel):
    id: PydanticObjectId
    description: str
    amount: float
    paid_by_member_id: str
    split_with_member_ids: List[str]
    split_type: Literal["equal", "exact"]
    custom_splits: List[CustomSplit]

class ItineraryItemUpdate(BaseModel):
    title: Optional[str] = None
    item_type: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    location: Optional[str] = None
    notes: Optional[str] = Field(default=None, max_length=2000)
    day_index: Optional[int] = Field(default=None, ge=1)
    all_day: Optional[bool] = None
    place_id: Optional[str] = Field(default=None, max_length=200)
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lng: Optional[float] = Field(default=None, ge=-180, le=180)

class ExpenseUpdate(BaseModel):
    description: Optional[str] = None
    amount: Optional[float] = None
    paid_by_member_id: Optional[str] = None
    split_with_member_ids: Optional[List[str]] = None
    split_type: Optional[Literal["equal", "exact"]] = None
    custom_splits: Optional[List[CustomSplit]] = None

class SettlementCreate(BaseModel):
    payer_member_id: str
    payee_member_id: str
    amount: float = Field(..., gt=0)
    mode: Literal["cash", "upi", "card"] = "upi"

class SettlementRead(BaseModel):
    id: PydanticObjectId
    payer_member_id: str
    payee_member_id: str
    amount: float
    mode: Literal["cash", "upi", "card"]

class SettlementUpdate(BaseModel):
    payer_member_id: Optional[str] = None
    payee_member_id: Optional[str] = None
    amount: Optional[float] = Field(default=None, gt=0)
    mode: Optional[Literal["cash", "upi", "card"]] = None

class BalanceEntry(BaseModel):
    member_id: str
    balance: float  # positive means others owe them; negative means they owe

class LinkExpiryUpdate(BaseModel):
    link_expires_at: Optional[datetime] = None

class TripLinkInfo(BaseModel):
    secret_access_url: str
    link_revoked: bool
    link_expires_at: Optional[datetime] = None
    access_token_version: int


# --- TripDoc + AI edit schemas ---
class JsonPatchOp(BaseModel):
    op: Literal["add", "remove", "replace"]
    path: str
    value: Optional[Any] = None


class TripDocGetResponse(BaseModel):
    schema_version: int
    timezone: str
    title: str
    date_range: Dict[str, Optional[date]]
    members: List[Dict[str, Any]]
    lodgings: List[Dict[str, Any]]
    natural_language_trip_brief: str
    shared_notes: str
    revision: int
    updated_at: datetime


class TripDocPatchRequest(BaseModel):
    patch: List[JsonPatchOp]
    client_revision: int = Field(..., ge=1)


class TripDocPatchResponse(TripDocGetResponse):
    pass


class ItineraryOp(BaseModel):
    op: Literal["create", "update", "delete"]
    id: Optional[str] = None
    temp_id: Optional[str] = None
    item: Optional[Dict[str, Any]] = None
    set: Optional[Dict[str, Any]] = None


class AiProposeEditsRequest(BaseModel):
    user_request: str = Field(..., max_length=4000)
    edit_doc: bool = True
    edit_itinerary: bool = True


class AiProposeEditsResponse(BaseModel):
    trip_doc_patch: List[JsonPatchOp] = Field(default_factory=list)
    itinerary_ops: List[ItineraryOp] = Field(default_factory=list)
    nonce: str
    nonce_expires_at: datetime


class AiApplyEditsRequest(BaseModel):
    trip_doc_patch: List[JsonPatchOp] = Field(default_factory=list)
    itinerary_ops: List[ItineraryOp] = Field(default_factory=list)
    client_revision: int = Field(..., ge=1)
    nonce: str


class AiApplyEditsResponse(BaseModel):
    trip_doc: TripDocGetResponse
    created_itinerary_ids: List[str] = Field(default_factory=list)
    updated_itinerary_ids: List[str] = Field(default_factory=list)
    deleted_itinerary_ids: List[str] = Field(default_factory=list)