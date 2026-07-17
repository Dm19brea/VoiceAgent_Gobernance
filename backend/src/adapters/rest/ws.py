"""WebSocket adapter: live supervision of active sessions (M5.5).

Thin peripheral adapter — it only reads the active-session store and streams it. On
connect it sends the current snapshot, then re-sends on a fixed interval until the
client disconnects.
"""

import asyncio
from typing import Annotated, Any

import jwt
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, WebSocketException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from src.adapters.rest.auth import verify_access_token
from src.application.ports.active_sessions import ActiveSessionSnapshot
from src.infrastructure.db.session import get_session
from src.infrastructure.redis.active_sessions import get_active_session_store

router = APIRouter()

ACTIVE_SESSIONS_INTERVAL = 2.0


async def authenticate_ws(
    websocket: WebSocket,
    session: Annotated[AsyncSession, Depends(get_session)],
    token: str | None = None,
) -> str:
    """WS auth dependency (S2): verifies the DB-backed access token BEFORE
    ``accept()``. Browsers can't set WS headers, so the token travels as
    ``?token=``. Raises ``WebSocketException(1008)`` — which Starlette
    closes pre-accept — on a missing, invalid, wrong-type, or revoked token.

    Overridden with a stub in tests exercising the streaming/serialization
    behavior without a DB (mirrors ``require_auth``'s ``_bypass_dashboard_auth``
    test seam).
    """
    if token is None:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
    try:
        return await verify_access_token(token, session)
    except jwt.PyJWTError as exc:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION) from exc


@router.websocket("/ws/active-sessions")
async def active_sessions_ws(
    websocket: WebSocket, _subject: Annotated[str, Depends(authenticate_ws)]
) -> None:
    """Stream active sessions to an authenticated dashboard client."""
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
