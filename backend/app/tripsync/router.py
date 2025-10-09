# FILE: ./app/tripsync/router.py (NEW FILE)
from fastapi import APIRouter, Depends, Request, HTTPException
from typing import List
from beanie import PydanticObjectId
from app.models.user import User
from app.auth.core import current_active_user
from .schemas import (
    TripCreate,
    TripRead,
    TripMemberInfo,
    TripMemberCreate,
    LinkSelfRequest,
    ItineraryItemCreate,
    ItineraryItemUpdate,
    ExpenseCreate,
    ExpenseUpdate,
    SettlementCreate,
    SettlementUpdate,
    BalanceEntry,
    LinkExpiryUpdate,
)
from app.models.trip import Trip, TripMember
from .deps import resolve_trip_actor
from .audit import record_audit
from .service import TripService
from slowapi import Limiter
from slowapi.util import get_remote_address

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

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
    trips = await Trip.find(Trip.members.user.id == user.id).to_list()
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
        for t in trips
    ]

@router.get("/access/{access_token}", response_model=TripRead)
@limiter.limit("30/minute")
async def preview_trip_by_access(access_token: str, request: Request):
    trip = await Trip.find_one(Trip.access_token == access_token)
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
    item = await TripService.add_itinerary_item(actor["trip"], payload)
    await record_audit(request, actor, "itinerary.create", {"item_id": str(item.id)})
    return {"id": str(item.id)}

@router.patch("/{trip_id}/itinerary/{item_id}")
@limiter.limit("60/minute")
async def update_itinerary(
    trip_id: PydanticObjectId,
    item_id: PydanticObjectId,
    payload: ItineraryItemUpdate,
    actor = Depends(resolve_trip_actor("trip_id")),
    request: Request = None,
):
    from app.models.itinerary import ItineraryItem
    item = await ItineraryItem.get(item_id)
    if not item or str(item.trip.id) != str(actor["trip"].id):
        raise HTTPException(status_code=404, detail="Itinerary item not found")
    update_data = {k: v for k, v in payload.model_dump().items() if v is not None}
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
    from app.models.itinerary import ItineraryItem
    item = await ItineraryItem.get(item_id)
    if not item or str(item.trip.id) != str(actor["trip"].id):
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
    paid_by_user = actor.get("actor_user")
    expense = await TripService.add_expense(actor["trip"], payload, paid_by_user=paid_by_user)
    await record_audit(request, actor, "expense.create", {"expense_id": str(expense.id)})
    return {"id": str(expense.id)}

@router.patch("/{trip_id}/expenses/{expense_id}")
@limiter.limit("60/minute")
async def update_expense(
    trip_id: PydanticObjectId,
    expense_id: PydanticObjectId,
    payload: ExpenseUpdate,
    actor = Depends(resolve_trip_actor("trip_id")),
    request: Request = None,
):
    from app.models.expense import Expense
    exp = await Expense.get(expense_id)
    if not exp or str(exp.trip.id) != str(actor["trip"].id):
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
    from app.models.expense import Expense
    exp = await Expense.get(expense_id)
    if not exp or str(exp.trip.id) != str(actor["trip"].id):
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
    settlement = await TripService.add_settlement(actor["trip"], payload)
    await record_audit(request, actor, "settlement.create", {"settlement_id": str(settlement.id)})
    return {"id": str(settlement.id)}

@router.patch("/{trip_id}/settlements/{settlement_id}")
@limiter.limit("60/minute")
async def update_settlement(
    trip_id: PydanticObjectId,
    settlement_id: PydanticObjectId,
    payload: SettlementUpdate,
    actor = Depends(resolve_trip_actor("trip_id")),
    request: Request = None,
):
    from app.models.settlement import Settlement
    s = await Settlement.get(settlement_id)
    if not s or str(s.trip.id) != str(actor["trip"].id):
        raise HTTPException(status_code=404, detail="Settlement not found")
    update_data = {k: v for k, v in payload.model_dump().items() if v is not None}
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
    from app.models.settlement import Settlement
    s = await Settlement.get(settlement_id)
    if not s or str(s.trip.id) != str(actor["trip"].id):
        raise HTTPException(status_code=404, detail="Settlement not found")
    await s.delete()
    await record_audit(request, actor, "settlement.delete", {"settlement_id": str(settlement_id)})
    return None


@router.get("/{trip_id}/balances", response_model=List[BalanceEntry])
@limiter.limit("60/minute")
async def get_balances(
    trip_id: PydanticObjectId,
    actor = Depends(resolve_trip_actor("trip_id")),
    request: Request = None,
):
    balances = await TripService.compute_balances(actor["trip"])
    return balances


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

@router.get("/{trip_id}/itinerary", response_model=List[ItineraryItemCreate])
async def list_itinerary(
    trip_id: PydanticObjectId,
    actor = Depends(resolve_trip_actor("trip_id")),
):
    from app.models.itinerary import ItineraryItem
    items = await ItineraryItem.find(ItineraryItem.trip.id == actor["trip"].id).to_list()
    return [
        ItineraryItemCreate(
            title=i.title,
            item_type=i.item_type,
            start_time=i.start_time,
            end_time=i.end_time,
            location=i.location,
        )
        for i in items
    ]

@router.get("/{trip_id}/expenses", response_model=List[ExpenseUpdate])
async def list_expenses(
    trip_id: PydanticObjectId,
    actor = Depends(resolve_trip_actor("trip_id")),
):
    from app.models.expense import Expense as ExpModel
    exps = await ExpModel.find(ExpModel.trip.id == actor["trip"].id).to_list()
    return [
        ExpenseUpdate(
            description=e.description,
            amount=e.amount,
            paid_by_member_id=e.paid_by_member_id,
            split_with_member_ids=e.split_with_member_ids,
        )
        for e in exps
    ]

@router.get("/{trip_id}/settlements", response_model=List[SettlementUpdate])
async def list_settlements(
    trip_id: PydanticObjectId,
    actor = Depends(resolve_trip_actor("trip_id")),
):
    from app.models.settlement import Settlement as SetModel
    sts = await SetModel.find(SetModel.trip.id == actor["trip"].id).to_list()
    return [
        SettlementUpdate(
            payer_member_id=s.payer_member_id,
            payee_member_id=s.payee_member_id,
            amount=s.amount,
        )
        for s in sts
    ]


# --- Link lifecycle (auth + membership) ---

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