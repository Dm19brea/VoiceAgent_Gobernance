"""Redis-backed store of active sessions + best-effort ingestion wiring (M5.4).

State lives in a single Redis hash (field = ``session_id``, value = JSON snapshot). It is
ephemeral: the source of truth is Postgres; this only powers live supervision (M5.5).
"""

import json
from datetime import datetime
from uuid import UUID

import redis.asyncio as redis

from src.application.commands import IngestEventCommand
from src.application.ports.active_sessions import ActiveSessionSnapshot, ActiveSessionStore
from src.application.ports.governance_repository import GovernanceRepository
from src.domain.enums import EventType
from src.infrastructure.config import settings

_HASH_KEY = "active_sessions"


class RedisActiveSessionStore:
    """``ActiveSessionStore`` backed by a Redis hash."""

    def __init__(self, client: redis.Redis | None = None, *, key: str = _HASH_KEY) -> None:
        self._client = client if client is not None else redis.from_url(settings.redis_url)
        self._key = key

    async def mark_active(self, snapshot: ActiveSessionSnapshot) -> None:
        await self._client.hset(self._key, snapshot.session_id, _encode(snapshot))

    async def mark_ended(self, session_id: str) -> None:
        await self._client.hdel(self._key, session_id)

    async def list_active(self) -> list[ActiveSessionSnapshot]:
        raw = await self._client.hgetall(self._key)
        return [_decode(value) for value in raw.values()]


_store: RedisActiveSessionStore | None = None


def get_active_session_store() -> RedisActiveSessionStore:
    """Return the process-wide store (lazily created; connects on first use)."""
    global _store
    if _store is None:
        _store = RedisActiveSessionStore()
    return _store


async def update_active_state(
    store: ActiveSessionStore,
    repository: GovernanceRepository,
    command: IngestEventCommand,
) -> None:
    """Reflect a just-ingested event in the active-session store (R7)."""
    if command.event_type is EventType.SESSION_STARTED:
        session = await repository.get_session(command.call_id)
        if session is not None:
            await store.mark_active(
                ActiveSessionSnapshot(
                    session_id=session.session_id,
                    agent_id=session.agent_id,
                    status=session.status.value,
                    started_at=session.started_at,
                )
            )
    elif command.event_type is EventType.SESSION_ENDED:
        await store.mark_ended(command.call_id)


def _encode(snapshot: ActiveSessionSnapshot) -> str:
    return json.dumps(
        {
            "session_id": snapshot.session_id,
            "agent_id": str(snapshot.agent_id),
            "status": snapshot.status,
            "started_at": snapshot.started_at.isoformat(),
        }
    )


def _decode(value: bytes | str) -> ActiveSessionSnapshot:
    data = json.loads(value)
    return ActiveSessionSnapshot(
        session_id=data["session_id"],
        agent_id=UUID(data["agent_id"]),
        status=data["status"],
        started_at=datetime.fromisoformat(data["started_at"]),
    )
