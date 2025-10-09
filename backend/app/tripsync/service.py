from typing import Optional
from beanie import PydanticObjectId

from app.models.trip import Trip, TripMember
from app.models.user import User
from app.models.itinerary import ItineraryItem
from app.models.expense import Expense
from app.models.settlement import Settlement
from app.tripsync.schemas import ExpenseCreate, ItineraryItemCreate, SettlementCreate, BalanceEntry


class TripService:
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
        )
        return await item.insert()

    @staticmethod
    async def add_expense(trip: Trip, data: ExpenseCreate, paid_by_user: Optional[User]) -> Expense:
        expense = Expense(
            trip=trip,
            description=data.description,
            amount=data.amount,
            paid_by_member_id=data.paid_by_member_id,
            split_with_member_ids=data.split_with_member_ids,
        )
        return await expense.insert()

    @staticmethod
    async def add_settlement(trip: Trip, data: SettlementCreate) -> Settlement:
        settlement = Settlement(
            trip=trip,
            payer_member_id=data.payer_member_id,
            payee_member_id=data.payee_member_id,
            amount=data.amount,
        )
        return await settlement.insert()

    @staticmethod
    async def compute_balances(trip: Trip) -> list[BalanceEntry]:
        member_ids = [str(m.member_id) for m in trip.members]
        balance_map = {mid: 0.0 for mid in member_ids}

        # Expenses: each split_with member owes amount / len(split_with)
        expenses = await Expense.find(Expense.trip.id == trip.id).to_list()
        for e in expenses:
            if not e.split_with_member_ids:
                continue
            share = e.amount / len(e.split_with_member_ids)
            # Payer gets credited full amount initially
            balance_map[e.paid_by_member_id] = balance_map.get(e.paid_by_member_id, 0.0) + e.amount
            # Each participant owes their share
            for mid in e.split_with_member_ids:
                balance_map[mid] = balance_map.get(mid, 0.0) - share

        # Settlements: money moved from payer -> payee
        settlements = await Settlement.find(Settlement.trip.id == trip.id).to_list()
        for s in settlements:
            balance_map[s.payer_member_id] = balance_map.get(s.payer_member_id, 0.0) - s.amount
            balance_map[s.payee_member_id] = balance_map.get(s.payee_member_id, 0.0) + s.amount

        return [BalanceEntry(member_id=mid, balance=round(bal, 2)) for mid, bal in balance_map.items()]


