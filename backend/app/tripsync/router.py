# FILE: ./app/tripsync/router.py (NEW FILE)
from fastapi import APIRouter, Depends, Request, HTTPException
from typing import Any, Dict, List
from beanie import PydanticObjectId
from datetime import datetime
import secrets
from pydantic import ValidationError
from app.models.user import User
from app.auth.core import current_active_user
from .schemas import (
    TripCreate,
    TripRead,
    TripMemberInfo,
    TripMemberCreate,
    LinkSelfRequest,
    ItineraryItemCreate,
    ItineraryItemRead,
    ItineraryItemUpdate,
    ExpenseCreate,
    ExpenseRead,
    ExpenseUpdate,
    SettlementCreate,
    SettlementRead,
    SettlementUpdate,
    BalanceEntry,
    LinkExpiryUpdate,
    TripLinkInfo,
    TripDocGetResponse,
    TripDocPatchRequest,
    TripDocPatchResponse,
    AiProposeEditsRequest,
    AiProposeEditsResponse,
    AiApplyEditsRequest,
    AiApplyEditsResponse,
    JsonPatchOp,
    ItineraryOp,
)
from app.models.trip import Trip, TripMember
from app.models.trip_doc import TripDoc
from app.models.trip_edit_nonce import TripEditNonce
from .deps import resolve_trip_actor
from .audit import record_audit
from .service import TripService
from .timezone import coerce_to_utc, ensure_end_not_before_start
from .json_patch import apply_json_patch, JsonPatchError
from .tripdoc_validators import normalize_tripdoc_dates, validate_patch_paths, validate_tripdoc_invariants
from .ai_client import get_openrouter_client, get_openrouter_model, get_openrouter_fallback_model, OpenRouterError
from .ai_prompts import TRIP_EDITOR_SYSTEM_PROMPT
from slowapi import Limiter
from slowapi.util import get_remote_address

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

def _require_quicklink_edit(actor: Dict[str, Any]) -> None:
    if actor.get("source") == "quicklink" and not actor.get("can_edit"):
        raise HTTPException(status_code=403, detail="Quicklink edit not enabled (send X-Trip-Edit: 1)")

@router.post("/", response_model=TripRead, status_code=201)
async def create_trip(
    trip_data: TripCreate,
    request: Request,
    user: User = Depends(current_active_user)
):
    new_trip = Trip(
        name=trip_data.name,
        description=trip_data.description,
        members=[
            TripMember(display_name=user.username, user=user, joined_via="login")
        ],
    )
    await new_trip.insert()

    base_url = str(request.base_url)
    access_url = f"{base_url}api/tripsync/access/{new_trip.access_token}"

    await record_audit(request, {"trip": new_trip, "source": "login", "actor_user": user}, "trip.create", {})

    return TripRead(
        id=new_trip.id,
        name=new_trip.name,
        description=new_trip.description,
        members=[
            TripMemberInfo(
                member_id=str(member.member_id),
                display_name=member.display_name,
                linked=bool(member.user),
            )
            for member in new_trip.members
        ],
        secret_access_url=access_url,
    )

@router.get("/my", response_model=List[TripRead])
async def get_my_trips(user: User = Depends(current_active_user)):
    # Fetch all trips with links resolved
    all_trips = await Trip.find_all(fetch_links=True).to_list()
    
    # Filter trips where the user is a linked member
    user_trips = [
        trip for trip in all_trips
        if any(
            member.user is not None and 
            (member.user.id == user.id if hasattr(member.user, 'id') else False)
            for member in trip.members
        )
    ]
    
    return [
        TripRead(
            id=t.id,
            name=t.name,
            description=t.description,
            members=[
                TripMemberInfo(
                    member_id=str(m.member_id),
                    display_name=m.display_name,
                    linked=bool(m.user),
                )
                for m in t.members
            ],
        )
        for t in user_trips
    ]

@router.get("/access/{access_token}", response_model=TripRead)
@limiter.limit("30/minute")
async def preview_trip_by_access(access_token: str, request: Request):
    parsed_uuid = None
    try:
        import uuid
        parsed_uuid = uuid.UUID(access_token)
    except Exception:
        parsed_uuid = None

    trip = await Trip.find_one(Trip.access_token == access_token)

    if (trip is None) and (parsed_uuid is not None):
        trip = await Trip.find_one(Trip.access_token == parsed_uuid)

    if not trip:
        raise HTTPException(status_code=404, detail="Invalid access link")
    return TripRead(
        id=trip.id,
        name=trip.name,
        description=trip.description,
        members=[
            TripMemberInfo(
                member_id=str(m.member_id),
                display_name=m.display_name,
                linked=bool(m.user),
            )
            for m in trip.members
        ],
        secret_access_url=None,
    )


# --- Member management ---

@router.post("/{trip_id}/members", response_model=TripRead)
@limiter.limit("60/minute")
async def add_member(
    trip_id: PydanticObjectId,
    payload: TripMemberCreate,
    actor = Depends(resolve_trip_actor("trip_id")),
    request: Request = None,
):
    _require_quicklink_edit(actor)
    trip = actor["trip"]
    trip = await TripService.add_member(trip, display_name=payload.display_name)
    await record_audit(request, actor, "member.create", {"display_name": payload.display_name})
    return TripRead(
        id=trip.id,
        name=trip.name,
        description=trip.description,
        members=[
            TripMemberInfo(member_id=str(m.member_id), display_name=m.display_name, linked=bool(m.user))
            for m in trip.members
        ],
    )

@router.post("/{trip_id}/members/link-self", response_model=TripRead)
async def link_self_member(
    trip_id: PydanticObjectId,
    payload: LinkSelfRequest,
    user: User = Depends(current_active_user),
    request: Request = None,
):
    trip = await Trip.get(trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    trip = await TripService.link_self(trip, user, member_id=payload.member_id)
    await record_audit(request, {"trip": trip, "actor_user": user, "source": "login"}, "member.link", {"member_id": payload.member_id})
    return TripRead(
        id=trip.id,
        name=trip.name,
        description=trip.description,
        members=[
            TripMemberInfo(member_id=str(m.member_id), display_name=m.display_name, linked=bool(m.user))
            for m in trip.members
        ],
    )


# --- Itinerary CRUD ---

@router.post("/{trip_id}/itinerary")
@limiter.limit("60/minute")
async def add_itinerary(
    trip_id: PydanticObjectId,
    payload: ItineraryItemCreate,
    actor = Depends(resolve_trip_actor("trip_id")),
    request: Request = None,
):
    _require_quicklink_edit(actor)
    # Place metadata must be complete if provided
    if (payload.lat is None) != (payload.lng is None):
        raise HTTPException(status_code=400, detail="lat and lng must be provided together")

    # Timezone contract: normalize to UTC at API boundary
    start_utc = coerce_to_utc(payload.start_time, assume_tz="UTC")
    end_utc = coerce_to_utc(payload.end_time, assume_tz="UTC") if payload.end_time else None
    try:
        ensure_end_not_before_start(start_utc, end_utc)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if payload.all_day:
        start_utc = start_utc.replace(hour=0, minute=0, second=0, microsecond=0)

    payload = payload.model_copy(update={"start_time": start_utc, "end_time": end_utc})
    item = await TripService.add_itinerary_item(actor["trip"], payload)
    await record_audit(request, actor, "itinerary.create", {"item_id": str(item.id)})
    return {"id": str(item.id)}

@router.get("/{trip_id}/itinerary/{item_id}")
@limiter.limit("60/minute")
async def get_itinerary_item(
    trip_id: PydanticObjectId,
    item_id: PydanticObjectId,
    actor = Depends(resolve_trip_actor("trip_id")),
    request: Request = None,
):
    """Get a single itinerary item by ID for editing"""
    from app.models.itinerary import ItineraryItem
    item = await ItineraryItem.get(item_id)
    if not item or str(item.trip.ref.id) != str(actor["trip"].id):
        raise HTTPException(status_code=404, detail="Itinerary item not found")
    return {
        "id": str(item.id),
        "title": item.title,
        "item_type": item.item_type,
        "start_time": item.start_time,
        "end_time": item.end_time,
        "location": item.location,
        "notes": getattr(item, "notes", None),
        "day_index": getattr(item, "day_index", None),
        "all_day": getattr(item, "all_day", False),
        "place_id": getattr(item, "place_id", None),
        "lat": getattr(item, "lat", None),
        "lng": getattr(item, "lng", None),
    }

@router.patch("/{trip_id}/itinerary/{item_id}")
@limiter.limit("60/minute")
async def update_itinerary(
    trip_id: PydanticObjectId,
    item_id: PydanticObjectId,
    payload: ItineraryItemUpdate,
    actor = Depends(resolve_trip_actor("trip_id")),
    request: Request = None,
):
    _require_quicklink_edit(actor)
    from app.models.itinerary import ItineraryItem
    item = await ItineraryItem.get(item_id)
    if not item or str(item.trip.ref.id) != str(actor["trip"].id):
        raise HTTPException(status_code=404, detail="Itinerary item not found")
    update_data = {k: v for k, v in payload.model_dump().items() if v is not None}

    # Validate merged place metadata
    merged_lat = update_data.get("lat", getattr(item, "lat", None))
    merged_lng = update_data.get("lng", getattr(item, "lng", None))
    if (merged_lat is None) != (merged_lng is None):
        raise HTTPException(status_code=400, detail="lat and lng must be provided together")

    # Normalize any updated times to UTC, and validate merged interval
    merged_start = update_data.get("start_time", item.start_time)
    merged_end = update_data.get("end_time", item.end_time)

    if "start_time" in update_data and update_data["start_time"] is not None:
        merged_start = coerce_to_utc(update_data["start_time"], assume_tz="UTC")
        update_data["start_time"] = merged_start
    else:
        merged_start = coerce_to_utc(merged_start, assume_tz="UTC") if merged_start else merged_start

    if "end_time" in update_data:
        merged_end = coerce_to_utc(update_data["end_time"], assume_tz="UTC") if update_data["end_time"] else None
        update_data["end_time"] = merged_end
    else:
        merged_end = coerce_to_utc(merged_end, assume_tz="UTC") if merged_end else None

    merged_all_day = update_data.get("all_day", getattr(item, "all_day", False))
    if merged_all_day and merged_start:
        merged_start = merged_start.replace(hour=0, minute=0, second=0, microsecond=0)
        update_data["start_time"] = merged_start

    try:
        ensure_end_not_before_start(merged_start, merged_end)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    for k, v in update_data.items():
        setattr(item, k, v)
    await item.save()
    await record_audit(request, actor, "itinerary.update", {"item_id": str(item.id)})
    return {"id": str(item.id)}

@router.delete("/{trip_id}/itinerary/{item_id}", status_code=204)
@limiter.limit("60/minute")
async def delete_itinerary(
    trip_id: PydanticObjectId,
    item_id: PydanticObjectId,
    actor = Depends(resolve_trip_actor("trip_id")),
    request: Request = None,
):
    _require_quicklink_edit(actor)
    from app.models.itinerary import ItineraryItem
    item = await ItineraryItem.get(item_id)
    if not item or str(item.trip.ref.id) != str(actor["trip"].id):
        raise HTTPException(status_code=404, detail="Itinerary item not found")
    await item.delete()
    await record_audit(request, actor, "itinerary.delete", {"item_id": str(item_id)})
    return None


# --- Expense CRUD ---

@router.post("/{trip_id}/expenses")
@limiter.limit("60/minute")
async def add_expense(
    trip_id: PydanticObjectId,
    payload: ExpenseCreate,
    actor = Depends(resolve_trip_actor("trip_id")),
    request: Request = None,
):
    _require_quicklink_edit(actor)
    paid_by_user = actor.get("actor_user")
    expense = await TripService.add_expense(actor["trip"], payload, paid_by_user=paid_by_user)
    await record_audit(request, actor, "expense.create", {"expense_id": str(expense.id)})
    return {"id": str(expense.id)}

@router.get("/{trip_id}/expenses/{expense_id}")
async def get_expense(
    trip_id: PydanticObjectId,
    expense_id: PydanticObjectId,
    actor = Depends(resolve_trip_actor("trip_id")),
):
    """Get a single expense by ID for editing"""
    from app.models.expense import Expense
    exp = await Expense.get(expense_id)
    if not exp or str(exp.trip.ref.id) != str(actor["trip"].id):
        raise HTTPException(status_code=404, detail="Expense not found")
    return {
        "id": str(exp.id),
        "description": exp.description,
        "amount": exp.amount,
        "paid_by_member_id": exp.paid_by_member_id,
        "split_with_member_ids": exp.split_with_member_ids,
    }

@router.patch("/{trip_id}/expenses/{expense_id}")
@limiter.limit("60/minute")
async def update_expense(
    trip_id: PydanticObjectId,
    expense_id: PydanticObjectId,
    payload: ExpenseUpdate,
    actor = Depends(resolve_trip_actor("trip_id")),
    request: Request = None,
):
    _require_quicklink_edit(actor)
    from app.models.expense import Expense
    exp = await Expense.get(expense_id)
    if not exp or str(exp.trip.ref.id) != str(actor["trip"].id):
        raise HTTPException(status_code=404, detail="Expense not found")
    update_data = {k: v for k, v in payload.model_dump().items() if v is not None}
    for k, v in update_data.items():
        setattr(exp, k, v)
    await exp.save()
    await record_audit(request, actor, "expense.update", {"expense_id": str(exp.id)})
    return {"id": str(exp.id)}

@router.delete("/{trip_id}/expenses/{expense_id}", status_code=204)
@limiter.limit("60/minute")
async def delete_expense(
    trip_id: PydanticObjectId,
    expense_id: PydanticObjectId,
    actor = Depends(resolve_trip_actor("trip_id")),
    request: Request = None,
):
    _require_quicklink_edit(actor)
    from app.models.expense import Expense
    exp = await Expense.get(expense_id)
    if not exp or str(exp.trip.ref.id) != str(actor["trip"].id):
        raise HTTPException(status_code=404, detail="Expense not found")
    await exp.delete()
    await record_audit(request, actor, "expense.delete", {"expense_id": str(expense_id)})
    return None


@router.post("/{trip_id}/settlements")
@limiter.limit("60/minute")
async def add_settlement(
    trip_id: PydanticObjectId,
    payload: SettlementCreate,
    actor = Depends(resolve_trip_actor("trip_id")),
    request: Request = None,
):
    _require_quicklink_edit(actor)
    settlement = await TripService.add_settlement(actor["trip"], payload)
    await record_audit(request, actor, "settlement.create", {"settlement_id": str(settlement.id)})
    return {"id": str(settlement.id)}

@router.get("/{trip_id}/settlements/{settlement_id}")
async def get_settlement(
    trip_id: PydanticObjectId,
    settlement_id: PydanticObjectId,
    actor = Depends(resolve_trip_actor("trip_id")),
):
    """Get a single settlement by ID for editing"""
    from app.models.settlement import Settlement
    s = await Settlement.get(settlement_id)
    if not s or str(s.trip.ref.id) != str(actor["trip"].id):
        raise HTTPException(status_code=404, detail="Settlement not found")
    return {
        "id": str(s.id),
        "payer_member_id": s.payer_member_id,
        "payee_member_id": s.payee_member_id,
        "amount": s.amount,
        "mode": s.mode,
    }

@router.patch("/{trip_id}/settlements/{settlement_id}")
@limiter.limit("60/minute")
async def update_settlement(
    trip_id: PydanticObjectId,
    settlement_id: PydanticObjectId,
    payload: SettlementUpdate,
    actor = Depends(resolve_trip_actor("trip_id")),
    request: Request = None,
):
    _require_quicklink_edit(actor)
    from app.models.settlement import Settlement
    s = await Settlement.get(settlement_id)
    if not s or str(s.trip.ref.id) != str(actor["trip"].id):
        raise HTTPException(status_code=404, detail="Settlement not found")

    update_data = {k: v for k, v in payload.model_dump().items() if v is not None}

    # Validate merged settlement state against trip membership and invariants.
    merged_payer = update_data.get("payer_member_id", s.payer_member_id)
    merged_payee = update_data.get("payee_member_id", s.payee_member_id)
    merged_amount = update_data.get("amount", s.amount)
    TripService._validate_settlement(actor["trip"], merged_payer, merged_payee, merged_amount)

    for k, v in update_data.items():
        setattr(s, k, v)
    await s.save()
    await record_audit(request, actor, "settlement.update", {"settlement_id": str(s.id)})
    return {"id": str(s.id)}

@router.delete("/{trip_id}/settlements/{settlement_id}", status_code=204)
@limiter.limit("60/minute")
async def delete_settlement(
    trip_id: PydanticObjectId,
    settlement_id: PydanticObjectId,
    actor = Depends(resolve_trip_actor("trip_id")),
    request: Request = None,
):
    _require_quicklink_edit(actor)
    from app.models.settlement import Settlement
    s = await Settlement.get(settlement_id)
    if not s or str(s.trip.ref.id) != str(actor["trip"].id):
        raise HTTPException(status_code=404, detail="Settlement not found")
    await s.delete()
    await record_audit(request, actor, "settlement.delete", {"settlement_id": str(settlement_id)})
    return None


async def _get_or_create_tripdoc(trip: Trip) -> TripDoc:
    existing = await TripDoc.find_one(TripDoc.trip.id == trip.id)
    if existing:
        return existing
    # Default doc: mirror core trip fields and members; keep segments empty.
    members = [
        {
            "member_id": str(m.member_id),
            "display_name": m.display_name,
            "travel_segments": [],
            "notes": None,
        }
        for m in trip.members
    ]
    new_doc = TripDoc(
        trip=trip,
        schema_version=2,
        timezone="UTC",
        title=trip.name,
        date_range={"start": None, "end": None},
        members=members,
        lodgings=[],
        natural_language_trip_brief=trip.description or "",
        shared_notes="",
        revision=1,
        updated_at=datetime.utcnow(),
    )
    return await new_doc.insert()


def _tripdoc_to_response(doc: TripDoc) -> TripDocGetResponse:
    d = doc.model_dump()
    # Be explicit: only expose the doc fields we support
    return TripDocGetResponse(
        schema_version=d.get("schema_version", 2),
        timezone=d.get("timezone", "UTC"),
        title=d.get("title", ""),
        date_range=d.get("date_range") or {"start": None, "end": None},
        members=d.get("members") or [],
        lodgings=d.get("lodgings") or [],
        natural_language_trip_brief=d.get("natural_language_trip_brief") or "",
        shared_notes=d.get("shared_notes") or "",
        revision=d.get("revision") or 1,
        updated_at=d.get("updated_at"),
    )


@router.get("/{trip_id}/doc", response_model=TripDocGetResponse)
async def get_trip_doc(
    trip_id: PydanticObjectId,
    actor=Depends(resolve_trip_actor("trip_id")),
):
    doc = await _get_or_create_tripdoc(actor["trip"])
    return _tripdoc_to_response(doc)


@router.patch("/{trip_id}/doc", response_model=TripDocPatchResponse)
@limiter.limit("10/minute")
async def patch_trip_doc(
    trip_id: PydanticObjectId,
    payload: TripDocPatchRequest,
    actor=Depends(resolve_trip_actor("trip_id")),
    request: Request = None,
):
    _require_quicklink_edit(actor)
    doc = await _get_or_create_tripdoc(actor["trip"])
    if doc.revision != payload.client_revision:
        raise HTTPException(status_code=409, detail="Trip doc revision conflict")

    allowed_prefixes = {
        "/title",
        "/timezone",
        "/date_range",
        "/members",
        "/lodgings",
        "/natural_language_trip_brief",
        "/shared_notes",
    }
    patch_ops = [p.model_dump(exclude_none=True) for p in payload.patch]
    try:
        validate_patch_paths(patch_ops, allowed_prefixes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Apply patch on a plain dict, validate invariants, then write back allowed fields.
    doc_dict = doc.model_dump()
    try:
        apply_json_patch(doc_dict, patch_ops)
    except JsonPatchError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Convert known date string fields produced by JSON patch into `date` objects.
    try:
        normalize_tripdoc_dates(doc_dict)
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid date format in patch values")

    allowed_member_ids = {str(m.member_id) for m in actor["trip"].members}
    try:
        validate_tripdoc_invariants(doc_dict, allowed_member_ids)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    for k in [
        "schema_version",
        "timezone",
        "title",
        "date_range",
        "members",
        "lodgings",
        "natural_language_trip_brief",
        "shared_notes",
    ]:
        setattr(doc, k, doc_dict.get(k))
    doc.revision += 1
    doc.updated_at = datetime.utcnow()
    await doc.save()
    await record_audit(request, actor, "tripdoc.patch", {"revision": doc.revision})
    return _tripdoc_to_response(doc)


@router.post("/{trip_id}/ai/propose-edits", response_model=AiProposeEditsResponse)
@limiter.limit("10/minute")
async def ai_propose_edits(
    trip_id: PydanticObjectId,
    payload: AiProposeEditsRequest,
    actor=Depends(resolve_trip_actor("trip_id")),
    request: Request = None,
):
    # Propose does not mutate DB state (other than issuing a nonce). Quicklink without edit gate is allowed to propose,
    # but the eventual apply requires X-Trip-Edit: 1.
    doc = await _get_or_create_tripdoc(actor["trip"])

    from app.models.itinerary import ItineraryItem
    itinerary = []
    if payload.edit_itinerary:
        items = await (
            ItineraryItem.find(ItineraryItem.trip.id == actor["trip"].id)
            .sort("start_time")
            .limit(200)
            .to_list()
        )
        itinerary = [
            {
                "id": str(i.id),
                "title": i.title,
                "item_type": i.item_type,
                "start_time": i.start_time.isoformat(),
                "end_time": i.end_time.isoformat() if i.end_time else None,
                "location": i.location,
                "notes": getattr(i, "notes", None),
                "day_index": getattr(i, "day_index", None),
                "all_day": getattr(i, "all_day", False),
                "place_id": getattr(i, "place_id", None),
                "lat": getattr(i, "lat", None),
                "lng": getattr(i, "lng", None),
            }
            for i in items
        ]

    client = None
    try:
        client = get_openrouter_client()
    except OpenRouterError as e:
        raise HTTPException(status_code=503, detail=str(e))
    model = get_openrouter_model()
    fallback = get_openrouter_fallback_model()

    user_payload = {
        "task": "edit_trip",
        "user_request": payload.user_request,
        "trip_doc": _tripdoc_to_response(doc).model_dump(),
        "itinerary_items": itinerary,
    }

    try:
        result = await client.chat_json(model=model, system_prompt=TRIP_EDITOR_SYSTEM_PROMPT, user_json=user_payload)
    except Exception as e:
        if fallback:
            try:
                result = await client.chat_json(model=fallback, system_prompt=TRIP_EDITOR_SYSTEM_PROMPT, user_json=user_payload)
            except Exception as e2:
                raise HTTPException(status_code=502, detail="AI propose failed")
        else:
            raise HTTPException(status_code=502, detail="AI propose failed")

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    trip_doc_patch = result.get("trip_doc_patch") or []
    itinerary_ops = result.get("itinerary_ops") or []

    # Issue a one-time nonce for apply.
    nonce = secrets.token_urlsafe(32)
    nonce_doc = TripEditNonce(trip_id=str(actor["trip"].id), nonce=nonce, purpose="ai_apply")
    await nonce_doc.insert()

    await record_audit(request, actor, "ai.propose", {"has_doc_patch": bool(trip_doc_patch), "ops": len(itinerary_ops)})

    return AiProposeEditsResponse(
        trip_doc_patch=[JsonPatchOp(**p) for p in trip_doc_patch],
        itinerary_ops=[ItineraryOp(**o) for o in itinerary_ops],
        nonce=nonce,
        nonce_expires_at=nonce_doc.expires_at,
    )


@router.post("/{trip_id}/ai/apply-edits", response_model=AiApplyEditsResponse)
@limiter.limit("10/minute")
async def ai_apply_edits(
    trip_id: PydanticObjectId,
    payload: AiApplyEditsRequest,
    actor=Depends(resolve_trip_actor("trip_id")),
    request: Request = None,
):
    _require_quicklink_edit(actor)

    # Validate nonce (one-time, short TTL)
    nonce_doc = await TripEditNonce.find_one(
        TripEditNonce.trip_id == str(actor["trip"].id),
        TripEditNonce.nonce == payload.nonce,
    )
    if not nonce_doc or nonce_doc.used_at is not None or nonce_doc.expires_at < datetime.utcnow():
        raise HTTPException(status_code=403, detail="Invalid or expired nonce")
    nonce_doc.used_at = datetime.utcnow()
    await nonce_doc.save()

    doc = await _get_or_create_tripdoc(actor["trip"])
    if doc.revision != payload.client_revision:
        raise HTTPException(status_code=409, detail="Trip doc revision conflict")

    allowed_prefixes = {
        "/title",
        "/timezone",
        "/date_range",
        "/members",
        "/lodgings",
        "/natural_language_trip_brief",
        "/shared_notes",
    }
    patch_ops = [p.model_dump(exclude_none=True) for p in payload.trip_doc_patch]
    try:
        validate_patch_paths(patch_ops, allowed_prefixes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Apply TripDoc patch if provided
    if patch_ops:
        doc_dict = doc.model_dump()
        try:
            apply_json_patch(doc_dict, patch_ops)
        except JsonPatchError as e:
            raise HTTPException(status_code=400, detail=str(e))
        try:
            normalize_tripdoc_dates(doc_dict)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid date format in patch values")
        allowed_member_ids = {str(m.member_id) for m in actor["trip"].members}
        try:
            validate_tripdoc_invariants(doc_dict, allowed_member_ids)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        for k in [
            "schema_version",
            "timezone",
            "title",
            "date_range",
            "members",
            "lodgings",
            "natural_language_trip_brief",
            "shared_notes",
        ]:
            setattr(doc, k, doc_dict.get(k))

    created_ids: List[str] = []
    updated_ids: List[str] = []
    deleted_ids: List[str] = []

    from app.models.itinerary import ItineraryItem

    for op in payload.itinerary_ops:
        if op.op == "create":
            item = op.item or {}
            if not item.get("title") or not item.get("item_type") or not item.get("start_time"):
                raise HTTPException(status_code=400, detail="Invalid itinerary create op")
            if (item.get("lat") is None) != (item.get("lng") is None):
                raise HTTPException(status_code=400, detail="lat and lng must be provided together")
            # Normalize invalid day_index coming from AI (schema requires >= 1).
            if "day_index" in item:
                try:
                    if item["day_index"] is None or int(item["day_index"]) >= 1:
                        item["day_index"] = int(item["day_index"]) if item["day_index"] is not None else None
                    else:
                        item["day_index"] = None
                except Exception:
                    item["day_index"] = None
            start = coerce_to_utc(datetime.fromisoformat(item["start_time"].replace("Z", "+00:00")), assume_tz="UTC")
            end = None
            if item.get("end_time"):
                end = coerce_to_utc(datetime.fromisoformat(item["end_time"].replace("Z", "+00:00")), assume_tz="UTC")
            try:
                ensure_end_not_before_start(start, end)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            if item.get("all_day"):
                start = start.replace(hour=0, minute=0, second=0, microsecond=0)
            try:
                new_item = ItineraryItem(
                    trip=actor["trip"],
                    title=item["title"],
                    item_type=item["item_type"],
                    start_time=start,
                    end_time=end,
                    location=item.get("location"),
                    notes=item.get("notes"),
                    day_index=item.get("day_index"),
                    all_day=bool(item.get("all_day", False)),
                    place_id=item.get("place_id"),
                    lat=item.get("lat"),
                    lng=item.get("lng"),
                )
            except ValidationError as e:
                raise HTTPException(status_code=400, detail="Invalid itinerary create payload")
            await new_item.insert()
            created_ids.append(str(new_item.id))

        elif op.op == "update":
            if not op.id or not op.set:
                raise HTTPException(status_code=400, detail="Invalid itinerary update op")
            item = await ItineraryItem.get(PydanticObjectId(op.id))
            if not item or str(item.trip.ref.id) != str(actor["trip"].id):
                raise HTTPException(status_code=404, detail="Itinerary item not found")

            update_data = {k: v for k, v in (op.set or {}).items() if v is not None}
            # Normalize invalid day_index coming from AI (schema requires >= 1).
            if "day_index" in update_data:
                try:
                    di = update_data.get("day_index")
                    if di is None:
                        pass
                    elif int(di) >= 1:
                        update_data["day_index"] = int(di)
                    else:
                        # Ignore invalid values instead of 500'ing
                        update_data.pop("day_index", None)
                except Exception:
                    update_data.pop("day_index", None)
            merged_lat = update_data.get("lat", getattr(item, "lat", None))
            merged_lng = update_data.get("lng", getattr(item, "lng", None))
            if (merged_lat is None) != (merged_lng is None):
                raise HTTPException(status_code=400, detail="lat and lng must be provided together")

            if "start_time" in update_data:
                start = coerce_to_utc(datetime.fromisoformat(str(update_data["start_time"]).replace("Z", "+00:00")), assume_tz="UTC")
                update_data["start_time"] = start
            else:
                start = coerce_to_utc(item.start_time, assume_tz="UTC")

            if "end_time" in update_data:
                end_val = update_data["end_time"]
                end = coerce_to_utc(datetime.fromisoformat(str(end_val).replace("Z", "+00:00")), assume_tz="UTC") if end_val else None
                update_data["end_time"] = end
            else:
                end = coerce_to_utc(item.end_time, assume_tz="UTC") if item.end_time else None

            merged_all_day = update_data.get("all_day", getattr(item, "all_day", False))
            if merged_all_day and start:
                start = start.replace(hour=0, minute=0, second=0, microsecond=0)
                update_data["start_time"] = start
            try:
                ensure_end_not_before_start(start, end)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

            for k, v in update_data.items():
                setattr(item, k, v)
            await item.save()
            updated_ids.append(str(item.id))

        elif op.op == "delete":
            if not op.id:
                raise HTTPException(status_code=400, detail="Invalid itinerary delete op")
            item = await ItineraryItem.get(PydanticObjectId(op.id))
            if not item or str(item.trip.ref.id) != str(actor["trip"].id):
                raise HTTPException(status_code=404, detail="Itinerary item not found")
            await item.delete()
            deleted_ids.append(op.id)

    doc.revision += 1
    doc.updated_at = datetime.utcnow()
    await doc.save()
    await record_audit(
        request,
        actor,
        "ai.apply",
        {"doc_patched": bool(patch_ops), "created": len(created_ids), "updated": len(updated_ids), "deleted": len(deleted_ids), "revision": doc.revision},
    )

    return AiApplyEditsResponse(
        trip_doc=_tripdoc_to_response(doc),
        created_itinerary_ids=created_ids,
        updated_itinerary_ids=updated_ids,
        deleted_itinerary_ids=deleted_ids,
    )


@router.get("/{trip_id}/balances", response_model=List[BalanceEntry])
@limiter.limit("60/minute")
async def get_balances(
    trip_id: PydanticObjectId,
    actor = Depends(resolve_trip_actor("trip_id")),
    request: Request = None,
):
    balances = await TripService.compute_balances(actor["trip"])
    return balances


# --- Link lifecycle (auth + membership) ---
# These routes must come before the generic GET /{trip_id} route

@router.get("/{trip_id}/link", response_model=TripLinkInfo)
async def get_trip_link(
    trip_id: PydanticObjectId,
    user: User = Depends(current_active_user),
    request: Request = None,
):
    """Get the current access link for a trip"""
    trip = await Trip.get(trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    
    # Only linked members can view the link
    is_member = any(m.user is not None and getattr(m.user, "id", None) == user.id for m in trip.members)
    if not is_member:
        raise HTTPException(status_code=403, detail="Not a trip member")
    
    base_url = str(request.base_url)
    access_url = f"{base_url}api/tripsync/access/{trip.access_token}"
    
    return TripLinkInfo(
        secret_access_url=access_url,
        link_revoked=trip.link_revoked,
        link_expires_at=trip.link_expires_at,
        access_token_version=trip.access_token_version,
    )

@router.post("/{trip_id}/rotate-link")
async def rotate_link(
    trip_id: PydanticObjectId,
    user: User = Depends(current_active_user),
    request: Request = None,
):
    import uuid
    trip = await Trip.get(trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    # Only linked members can manage links
    is_member = any(m.user is not None and getattr(m.user, "id", None) == user.id for m in trip.members)
    if not is_member:
        raise HTTPException(status_code=403, detail="Not a trip member")
    trip.access_token = uuid.uuid4()
    trip.access_token_version += 1
    trip.link_revoked = False
    await trip.save()
    await record_audit(request, {"trip": trip, "actor_user": user, "source": "login"}, "link.rotate", {})
    return {"secret_access_url": f"/api/tripsync/access/{trip.access_token}"}

@router.post("/{trip_id}/revoke-link", status_code=204)
async def revoke_link(
    trip_id: PydanticObjectId,
    user: User = Depends(current_active_user),
    request: Request = None,
):
    trip = await Trip.get(trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    is_member = any(m.user is not None and getattr(m.user, "id", None) == user.id for m in trip.members)
    if not is_member:
        raise HTTPException(status_code=403, detail="Not a trip member")
    trip.link_revoked = True
    await trip.save()
    await record_audit(request, {"trip": trip, "actor_user": user, "source": "login"}, "link.revoke", {})
    return None

@router.patch("/{trip_id}/link-expiry")
async def update_link_expiry(
    trip_id: PydanticObjectId,
    payload: LinkExpiryUpdate,
    user: User = Depends(current_active_user),
    request: Request = None,
):
    trip = await Trip.get(trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    is_member = any(m.user is not None and getattr(m.user, "id", None) == user.id for m in trip.members)
    if not is_member:
        raise HTTPException(status_code=403, detail="Not a trip member")
    trip.link_expires_at = payload.link_expires_at
    await trip.save()
    await record_audit(request, {"trip": trip, "actor_user": user, "source": "login"}, "link.expiry", {"link_expires_at": payload.link_expires_at.isoformat() if payload.link_expires_at else None})
    return {"link_expires_at": trip.link_expires_at}


# --- GET listings ---

@router.get("/{trip_id}", response_model=TripRead)
async def get_trip_details(
    trip_id: PydanticObjectId,
    actor = Depends(resolve_trip_actor("trip_id")),
):
    trip = actor["trip"]
    return TripRead(
        id=trip.id,
        name=trip.name,
        description=trip.description,
        members=[
            TripMemberInfo(member_id=str(m.member_id), display_name=m.display_name, linked=bool(m.user))
            for m in trip.members
        ],
    )

@router.get("/{trip_id}/itinerary", response_model=List[ItineraryItemRead])
async def list_itinerary(
    trip_id: PydanticObjectId,
    actor = Depends(resolve_trip_actor("trip_id")),
):
    from app.models.itinerary import ItineraryItem
    items = await (
        ItineraryItem.find(ItineraryItem.trip.id == actor["trip"].id)
        .sort("start_time")
        .to_list()
    )
    return [
        ItineraryItemRead(
            id=i.id,
            title=i.title,
            item_type=i.item_type,
            start_time=i.start_time,
            end_time=i.end_time,
            location=i.location,
            notes=getattr(i, "notes", None),
            day_index=getattr(i, "day_index", None),
            all_day=getattr(i, "all_day", False),
            place_id=getattr(i, "place_id", None),
            lat=getattr(i, "lat", None),
            lng=getattr(i, "lng", None),
        )
        for i in items
    ]

@router.get("/{trip_id}/expenses", response_model=List[ExpenseRead])
async def list_expenses(
    trip_id: PydanticObjectId,
    actor = Depends(resolve_trip_actor("trip_id")),
):
    from app.models.expense import Expense as ExpModel
    exps = await ExpModel.find(ExpModel.trip.id == actor["trip"].id).to_list()
    return [
        ExpenseRead(
            id=e.id,
            description=e.description,
            amount=e.amount,
            paid_by_member_id=e.paid_by_member_id,
            split_with_member_ids=e.split_with_member_ids,
        )
        for e in exps
    ]

@router.get("/{trip_id}/settlements", response_model=List[SettlementRead])
async def list_settlements(
    trip_id: PydanticObjectId,
    actor = Depends(resolve_trip_actor("trip_id")),
):
    from app.models.settlement import Settlement as SetModel
    sts = await SetModel.find(SetModel.trip.id == actor["trip"].id).to_list()
    return [
        SettlementRead(
            id=s.id,
            payer_member_id=s.payer_member_id,
            payee_member_id=s.payee_member_id,
            amount=s.amount,
            mode=s.mode,
        )
        for s in sts
    ]