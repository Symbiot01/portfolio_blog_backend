from typing import Optional, Literal, TypedDict
from fastapi import Depends, HTTPException, Request
from beanie import PydanticObjectId
from datetime import datetime

from app.auth.core import current_optional_user
from app.models.user import User
from app.models.trip import Trip, TripMember


class ActorContext(TypedDict, total=False):
    trip: Trip
    actor_user: Optional[User]
    actor_member_id: Optional[str]
    source: Literal["login", "quicklink"]
    can_edit: bool
    can_ai_edit: bool


def resolve_trip_actor(param_trip_id: str):
    async def _resolver(
        request: Request,
        user: Optional[User] = Depends(current_optional_user),
        trip_id: PydanticObjectId = None,
    ) -> ActorContext:
        # Path param must be provided by the route signature
        if trip_id is None:
            raise HTTPException(status_code=400, detail="trip_id is required")

        trip = await Trip.get(trip_id)
        if not trip:
            raise HTTPException(status_code=404, detail="Trip not found")

        # If user is authenticated and linked as member → allow via login
        if user is not None:
            is_linked_member = any(m.user is not None and getattr(m.user, "id", None) == user.id for m in trip.members)
            if is_linked_member:
                linked_member = next(m for m in trip.members if m.user is not None and getattr(m.user, "id", None) == user.id)
                return {
                    "trip": trip,
                    "actor_user": user,
                    "actor_member_id": str(linked_member.member_id),
                    "source": "login",
                    "can_edit": True,
                    "can_ai_edit": True,
                }
            # Not a linked member → fall through to quicklink if provided

        # Quicklink path: header or query
        # Check link lifecycle (quicklink only). Logged-in linked members should still have access.
        if trip.link_revoked:
            raise HTTPException(status_code=403, detail="Access link revoked")
        if trip.link_expires_at and datetime.utcnow() > trip.link_expires_at:
            raise HTTPException(status_code=403, detail="Access link expired")

        access_token = request.headers.get("X-Trip-Access") or request.query_params.get("access_token")
        if not access_token:
            raise HTTPException(status_code=403, detail="Not authorized for this trip")

        # Validate access token matches this trip
        try:
            token_matches = str(trip.access_token) == str(access_token)
        except Exception:
            token_matches = False
        if not token_matches:
            raise HTTPException(status_code=403, detail="Invalid access token for this trip")

        # Explicit edit gate for quicklink-based mutations (prevents accidental writes with just a shared URL).
        quicklink_edit_enabled = request.headers.get("X-Trip-Edit") == "1"

        # Optional attribution via member id header/query
        as_member_id = request.headers.get("X-Trip-As-Member") or request.query_params.get("as_member_id")
        actor_member_id: Optional[str] = None
        if as_member_id:
            member = next((m for m in trip.members if str(m.member_id) == str(as_member_id)), None)
            if member is not None:
                actor_member_id = str(member.member_id)

        return {
            "trip": trip,
            "actor_user": None,
            "actor_member_id": actor_member_id,
            "source": "quicklink",
            "can_edit": quicklink_edit_enabled,
            "can_ai_edit": quicklink_edit_enabled,
        }

    return _resolver


