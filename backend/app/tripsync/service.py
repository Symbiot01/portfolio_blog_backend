from typing import Optional
import math

from fastapi import HTTPException
from beanie import PydanticObjectId

from app.models.trip import Trip, TripMember
from app.models.user import User
from app.models.itinerary import ItineraryItem
from app.models.expense import Expense
from app.models.settlement import Settlement
from app.tripsync.schemas import ExpenseCreate, ItineraryItemCreate, SettlementCreate, BalanceEntry
from app.tripsync.balance_math import apply_settlement


class TripService:
    @staticmethod
    def _validate_settlement(trip: Trip, payer_member_id: str, payee_member_id: str, amount: float) -> None:
        if payer_member_id == payee_member_id:
            raise HTTPException(status_code=400, detail="payer_member_id and payee_member_id must be different")
        if not math.isfinite(amount) or amount <= 0:
            raise HTTPException(status_code=400, detail="amount must be a finite positive number")

        member_ids = {str(m.member_id) for m in trip.members}
        if payer_member_id not in member_ids:
            raise HTTPException(status_code=400, detail="payer_member_id is not a member of this trip")
        if payee_member_id not in member_ids:
            raise HTTPException(status_code=400, detail="payee_member_id is not a member of this trip")

    @staticmethod
    async def add_member(trip: Trip, display_name: str, user: Optional[User] = None) -> Trip:
        # Prevent duplicate linked member for same user within a trip
        if user is not None:
            if any(m.user is not None and getattr(m.user, "id", None) == user.id for m in trip.members):
                return trip
        trip.members.append(
            TripMember(display_name=display_name, user=user, joined_via="login" if user else "quicklink")
        )
        await trip.save()
        return trip

    @staticmethod
    async def link_self(trip: Trip, user: User, member_id: Optional[str]) -> Trip:
        # If already linked, do nothing
        if any(m.user is not None and getattr(m.user, "id", None) == user.id for m in trip.members):
            return trip

        # Try to link provided member_id first
        target = None
        if member_id:
            target = next((m for m in trip.members if str(m.member_id) == str(member_id) and m.user is None), None)
        # If not found, create a new linked member
        if target is None:
            trip.members.append(TripMember(display_name=user.username, user=user, joined_via="login"))
        else:
            target.user = user
        await trip.save()
        return trip

    @staticmethod
    async def add_itinerary_item(trip: Trip, data: ItineraryItemCreate) -> ItineraryItem:
        item = ItineraryItem(
            trip=trip,
            title=data.title,
            item_type=data.item_type,
            start_time=data.start_time,
            end_time=data.end_time,
            location=data.location,
            notes=getattr(data, "notes", None),
            day_index=getattr(data, "day_index", None),
            all_day=getattr(data, "all_day", False),
            place_id=getattr(data, "place_id", None),
            lat=getattr(data, "lat", None),
            lng=getattr(data, "lng", None),
        )
        return await item.insert()

    @staticmethod
    def _validate_expense(
        trip: Trip,
        amount: float,
        paid_by_member_id: str,
        split_type: str,
        split_with_member_ids: Optional[list[str]],
        custom_splits: Optional[list],
    ) -> list[str]:
        if not math.isfinite(amount) or amount <= 0:
            raise HTTPException(status_code=400, detail="Expense amount must be a finite positive number")

        member_ids = {str(m.member_id) for m in trip.members}
        if paid_by_member_id not in member_ids:
            raise HTTPException(status_code=400, detail="paid_by_member_id is not a member of this trip")

        deduped_split_with = list(dict.fromkeys(str(m_id) for m_id in (split_with_member_ids or [])))

        if split_type == "exact":
            if not custom_splits:
                raise HTTPException(status_code=400, detail="custom_splits must be provided for exact split type")

            total_custom_amount = 0.0
            seen_custom_members: set[str] = set()
            for cs in custom_splits:
                m_id = str(cs["member_id"] if isinstance(cs, dict) else getattr(cs, "member_id", ""))
                cs_amt = cs["amount"] if isinstance(cs, dict) else getattr(cs, "amount", 0.0)
                if m_id not in member_ids:
                    raise HTTPException(status_code=400, detail=f"Member {m_id} is not part of this trip")
                if m_id in seen_custom_members:
                    raise HTTPException(status_code=400, detail=f"Duplicate member_id {m_id} in custom_splits")
                seen_custom_members.add(m_id)
                if not math.isfinite(cs_amt) or cs_amt < 0:
                    raise HTTPException(status_code=400, detail="Custom split amounts must be finite non-negative numbers")
                total_custom_amount += cs_amt

            if not math.isclose(total_custom_amount, amount, rel_tol=1e-9, abs_tol=0.01):
                raise HTTPException(status_code=400, detail="Sum of custom splits must equal the total amount")
        else:
            if not deduped_split_with:
                raise HTTPException(status_code=400, detail="At least one member must be selected for equal split")
            for m_id in deduped_split_with:
                if m_id not in member_ids:
                    raise HTTPException(status_code=400, detail=f"Member {m_id} is not part of this trip")

        return deduped_split_with

    @staticmethod
    async def add_expense(trip: Trip, data: ExpenseCreate, paid_by_user: Optional[User]) -> Expense:
        deduped_split_with = TripService._validate_expense(
            trip=trip,
            amount=data.amount,
            paid_by_member_id=data.paid_by_member_id,
            split_type=data.split_type,
            split_with_member_ids=data.split_with_member_ids,
            custom_splits=data.custom_splits,
        )

        expense = Expense(
            trip=trip,
            description=data.description,
            amount=data.amount,
            paid_by_member_id=data.paid_by_member_id,
            split_with_member_ids=deduped_split_with,
            split_type=data.split_type,
            custom_splits=[cs.model_dump() if hasattr(cs, "model_dump") else cs.dict() for cs in data.custom_splits] if data.custom_splits else [],
            category=(data.category or "Other").strip() or "Other",
            date=data.date,
        )
        return await expense.insert()

    @staticmethod
    async def add_settlement(trip: Trip, data: SettlementCreate) -> Settlement:
        TripService._validate_settlement(trip, data.payer_member_id, data.payee_member_id, data.amount)
        settlement = Settlement(
            trip=trip,
            payer_member_id=data.payer_member_id,
            payee_member_id=data.payee_member_id,
            amount=data.amount,
            mode=data.mode or "upi",
        )
        return await settlement.insert()

    @staticmethod
    def _is_member_referenced(
        member_id: str,
        expenses: list,
        settlements: list,
    ) -> bool:
        target = str(member_id)
        for e in expenses:
            if str(getattr(e, "paid_by_member_id", "")) == target:
                return True
            if any(str(mid) == target for mid in (getattr(e, "split_with_member_ids", None) or [])):
                return True
            for cs in getattr(e, "custom_splits", None) or []:
                cs_mid = cs.get("member_id") if isinstance(cs, dict) else getattr(cs, "member_id", "")
                if str(cs_mid) == target:
                    return True

        for s in settlements:
            if str(getattr(s, "payer_member_id", "")) == target or str(getattr(s, "payee_member_id", "")) == target:
                return True

        return False

    @staticmethod
    def _validate_member_removal(
        trip: Trip,
        member_id: str,
        expenses: list,
        settlements: list,
    ) -> None:
        target = str(member_id)
        existing = next((m for m in trip.members if str(m.member_id) == target), None)
        if existing is None:
            raise HTTPException(status_code=404, detail="Member not found in this trip")
        if len(trip.members) <= 1:
            raise HTTPException(status_code=400, detail="Cannot remove the last remaining member of a trip")
        if TripService._is_member_referenced(target, expenses, settlements):
            raise HTTPException(
                status_code=400,
                detail="Cannot remove member who is referenced in existing expenses or settlements",
            )

    @staticmethod
    async def remove_member(trip: Trip, member_id: str) -> Trip:
        expenses = await Expense.find(Expense.trip.id == trip.id).to_list()
        settlements = await Settlement.find(Settlement.trip.id == trip.id).to_list()
        TripService._validate_member_removal(trip, member_id, expenses, settlements)
        target = str(member_id)
        trip.members = [m for m in trip.members if str(m.member_id) != target]
        await trip.save()
        return trip

    @staticmethod
    def _compute_balances_from_records(
        trip: Trip,
        expenses: list,
        settlements: list,
    ) -> list[BalanceEntry]:
        member_names = {str(m.member_id): m.display_name for m in trip.members}
        balance_map = {mid: 0.0 for mid in member_names}

        for e in expenses:
            payer_id = str(e.paid_by_member_id)
            balance_map[payer_id] = balance_map.get(payer_id, 0.0) + e.amount

            split_type = getattr(e, "split_type", "equal")

            if split_type == "exact":
                custom_splits = getattr(e, "custom_splits", []) or []
                seen_custom: set[str] = set()
                for cs in custom_splits:
                    member_id = cs.get("member_id") if isinstance(cs, dict) else getattr(cs, "member_id", None)
                    amount = cs.get("amount") if isinstance(cs, dict) else getattr(cs, "amount", 0.0)
                    if member_id:
                        mid_str = str(member_id)
                        if mid_str in seen_custom:
                            continue
                        seen_custom.add(mid_str)
                        balance_map[mid_str] = balance_map.get(mid_str, 0.0) - amount
            else:
                unique_participants = list(
                    dict.fromkeys(str(mid) for mid in (e.split_with_member_ids or []) if mid)
                )
                if not unique_participants:
                    continue
                share = e.amount / len(unique_participants)
                for mid in unique_participants:
                    balance_map[mid] = balance_map.get(mid, 0.0) - share

        for s in settlements:
            try:
                apply_settlement(balance_map, str(s.payer_member_id), str(s.payee_member_id), s.amount)
            except ValueError:
                continue

        entries: list[BalanceEntry] = []
        for mid, bal in balance_map.items():
            rounded = round(bal, 2)
            if mid in member_names or abs(rounded) > 0.0:
                entries.append(
                    BalanceEntry(
                        member_id=mid,
                        display_name=member_names.get(mid, "Former Member"),
                        balance=rounded,
                    )
                )
        return entries

    @staticmethod
    async def compute_balances(trip: Trip) -> list[BalanceEntry]:
        expenses = await Expense.find(Expense.trip.id == trip.id).to_list()
        settlements = await Settlement.find(Settlement.trip.id == trip.id).to_list()
        return TripService._compute_balances_from_records(trip, expenses, settlements)


