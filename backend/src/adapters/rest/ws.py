"""WebSocket adapter: live supervision of active sessions (M5.5).

Thin peripheral adapter — it only reads the active-session store and streams it. On
connect it sends the current snapshot, then re-sends on a fixed interval until the
client disconnects.
"""

import asyncio
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.application.ports.active_sessions import ActiveSessionSnapshot
from src.infrastructure.redis.active_sessions import get_active_session_store

router = APIRouter()

ACTIVE_SESSIONS_INTERVAL = 2.0


@router.websocket("/ws/active-sessions")
async def active_sessions_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    store = get_active_session_store()
    try:
        while True:
            snapshots = await store.list_active()
            await websocket.send_json([_to_dict(snapshot) for snapshot in snapshots])
            await asyncio.sleep(ACTIVE_SESSIONS_INTERVAL)
    except WebSocketDisconnect:
        return


def _to_dict(snapshot: ActiveSessionSnapshot) -> dict[str, Any]:
    return {
        "session_id": snapshot.session_id,
        "agent_id": str(snapshot.agent_id),
        "status": snapshot.status,
        "started_at": snapshot.started_at.isoformat(),
        "speaking_role": snapshot.speaking_role,
        "last_interruption_at": (
            snapshot.last_interruption_at.isoformat()
            if snapshot.last_interruption_at is not None
            else None
        ),
    }
