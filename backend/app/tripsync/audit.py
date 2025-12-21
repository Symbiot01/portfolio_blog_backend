from datetime import datetime
from typing import Any, Dict
from fastapi import Request

from app.tripsync.deps import ActorContext
from app.models.trip_audit import TripAuditEvent


async def record_audit(request: Request, actor: ActorContext, action: str, metadata: Dict[str, Any]) -> None:
    try:
        client_ip = request.client.host if request and request.client else None
    except Exception:
        client_ip = None

    trip_id = str(actor["trip"].id) if actor.get("trip") else None
    if not trip_id:
        return

    # Persist audit events (avoid printing secrets to stdout in production).
    event = TripAuditEvent(
        ts=datetime.utcnow(),
        trip_id=trip_id,
        source=actor.get("source") or "login",
        actor_user_id=str(actor["actor_user"].id) if actor.get("actor_user") else None,
        actor_member_id=actor.get("actor_member_id"),
        action=action,
        metadata=metadata or {},
        client_ip=client_ip,
    )
    try:
        await event.insert()
    except Exception:
        # Don't break business flows if audit insert fails.
        return


