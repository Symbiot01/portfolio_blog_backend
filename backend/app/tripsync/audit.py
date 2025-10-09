from datetime import datetime
from typing import Any, Dict
from fastapi import Request

from app.tripsync.deps import ActorContext


async def record_audit(request: Request, actor: ActorContext, action: str, metadata: Dict[str, Any]) -> None:
    # Minimal implementation: print to stdout; can be replaced with DB model later
    try:
        client_ip = request.client.host if request and request.client else None
    except Exception:
        client_ip = None

    log = {
        "ts": datetime.utcnow().isoformat(),
        "trip_id": str(actor["trip"].id) if actor.get("trip") else None,
        "source": actor.get("source"),
        "actor_user_id": str(actor["actor_user"].id) if actor.get("actor_user") else None,
        "actor_member_id": actor.get("actor_member_id"),
        "action": action,
        "metadata": metadata,
        "client_ip": client_ip,
    }
    print("AUDIT", log)


