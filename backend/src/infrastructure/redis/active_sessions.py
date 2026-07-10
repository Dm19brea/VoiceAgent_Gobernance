"""Redis-backed store of active sessions + best-effort ingestion wiring (M5.4).

State lives in a single Redis hash (field = ``session_id``, value = JSON snapshot). It is
ephemeral: the source of truth is Postgres; this only powers live supervision (M5.5).
"""

import json
from datetime import datetime
from typing import Protocol
from uuid import UUID

import redis.asyncio as redis

from src.application.commands import IngestEventCommand
from src.application.ports.active_sessions import ActiveSessionSnapshot, ActiveSessionStore
from src.domain.enums import EventType, Source
from src.domain.session import Session
from src.infrastructure.config import settings

_HASH_KEY = "active_sessions"

# Sentinel distinct from any real field value (role strings / ISO timestamps) so the
# Lua script can tell "explicit null" apart from "no update for this field".
_NULL_SENTINEL = "\0null"

# Atomically HGET -> merge (cjson) -> HSET in one round trip so two concurrent
# cross-field updates on the same session (e.g. set_speaking_role + mark_interruption)
# cannot interleave and clobber each other. No-op (returns false) if the session is absent.
_MERGE_SCRIPT = """
local raw = redis.call('HGET', KEYS[1], ARGV[1])
if not raw then
  return false
end
local snapshot = cjson.decode(raw)
for i = 2, #ARGV, 2 do
  local field = ARGV[i]
  local value = ARGV[i + 1]
  if value == '\\0null' then
    snapshot[field] = cjson.null
  else
    snapshot[field] = value
  end
end
local encoded = cjson.encode(snapshot)
redis.call('HSET', KEYS[1], ARGV[1], encoded)
return encoded
"""

# Atomically HGET -> (create-default | overwrite lifecycle fields only) -> HSET in one round
# trip so a duplicate SESSION_STARTED can never lose a concurrent set_speaking_role /
# mark_interruption update on the same session (same race class fixed by _MERGE_SCRIPT above,
# applied to the SESSION_STARTED path). If the session is absent, the snapshot is created with
# default (null) live fields; if present, only the lifecycle fields passed in ARGV are
# overwritten and the existing speaking_role/last_interruption_at are left untouched.
_UPSERT_LIFECYCLE_SCRIPT = """
local raw = redis.call('HGET', KEYS[1], ARGV[1])
local snapshot
if raw then
  snapshot = cjson.decode(raw)
else
  snapshot = {}
  snapshot['speaking_role'] = cjson.null
  snapshot['last_interruption_at'] = cjson.null
end
for i = 2, #ARGV, 2 do
  local field = ARGV[i]
  local value = ARGV[i + 1]
  if value == '\\0null' then
    snapshot[field] = cjson.null
  else
    snapshot[field] = value
  end
end
local encoded = cjson.encode(snapshot)
redis.call('HSET', KEYS[1], ARGV[1], encoded)
return encoded
"""


class RedisActiveSessionStore:
    """``ActiveSessionStore`` backed by a Redis hash."""

    def __init__(self, client: redis.Redis | None = None, *, key: str = _HASH_KEY) -> None:
        self._client = client if client is not None else redis.from_url(settings.redis_url)
        self._key = key

    async def mark_active(self, snapshot: ActiveSessionSnapshot) -> None:
        await self._client.hset(self._key, snapshot.session_id, _encode(snapshot))

    async def upsert_lifecycle(self, snapshot: ActiveSessionSnapshot) -> None:
        """Atomically write lifecycle fields, preserving live fields (speaking_role /
        last_interruption_at) of an existing entry, or creating one with default live
        fields if absent.

        Runs server-side as a single Lua script (EVAL: HGET -> mutate -> HSET) so a
        duplicate SESSION_STARTED cannot race a concurrent set_speaking_role /
        mark_interruption on the same session_id and lose that update (O(1), no
        list_active()/HGETALL scan).
        """
        args = [
            snapshot.session_id,
            "session_id",
            snapshot.session_id,
            "agent_id",
            str(snapshot.agent_id),
            "status",
            snapshot.status,
            "started_at",
            snapshot.started_at.isoformat(),
        ]
        await self._client.eval(_UPSERT_LIFECYCLE_SCRIPT, 1, self._key, *args)

    async def mark_ended(self, session_id: str) -> None:
        await self._client.hdel(self._key, session_id)

    async def list_active(self) -> list[ActiveSessionSnapshot]:
        raw = await self._client.hgetall(self._key)
        return [_decode(value) for value in raw.values()]

    async def set_speaking_role(self, session_id: str, role: str | None) -> None:
        await self._merge(session_id, speaking_role=role)

    async def mark_interruption(self, session_id: str, at: datetime) -> None:
        await self._merge(session_id, last_interruption_at=at)

    async def _merge(self, session_id: str, **updates: object) -> None:
        """Atomically read-modify-write fields onto the stored snapshot; no-op if absent.

        Runs server-side as a single Lua script (EVAL) so two concurrent merges on the
        same session_id cannot interleave and lose one of the updates.
        """
        args: list[str] = [session_id]
        for field, value in updates.items():
            args.append(field)
            if value is None:
                args.append(_NULL_SENTINEL)
            elif isinstance(value, datetime):
                args.append(value.isoformat())
            else:
                args.append(str(value))
        await self._client.eval(_MERGE_SCRIPT, 1, self._key, *args)


_store: RedisActiveSessionStore | None = None


def get_active_session_store() -> RedisActiveSessionStore:
    """Return the process-wide store (lazily created; connects on first use)."""
    global _store
    if _store is None:
        _store = RedisActiveSessionStore()
    return _store


class _SessionReader(Protocol):
    """Minimal read port: update_active_state only needs to load a session."""

    async def get_session(self, session_id: str) -> Session | None: ...


async def update_active_state(
    store: ActiveSessionStore,
    repository: _SessionReader,
    command: IngestEventCommand,
) -> None:
    """Reflect a just-ingested event in the active-session store (R7)."""
    if command.event_type is EventType.SESSION_STARTED:
        session = await repository.get_session(command.call_id)
        if session is not None:
            # Atomic upsert: preserves speaking_role/last_interruption_at of an existing
            # entry (a resent status-update:in-progress must not race and clobber a
            # concurrent TURN_STARTED/INTERRUPTION update), or defaults them if absent.
            await store.upsert_lifecycle(
                ActiveSessionSnapshot(
                    session_id=session.session_id,
                    agent_id=session.agent_id,
                    status=session.status.value,
                    started_at=session.started_at,
                )
            )
    elif command.event_type in (EventType.SESSION_ENDED, EventType.SESSION_FAILED):
        await store.mark_ended(command.call_id)
    elif command.event_type is EventType.CONVERSATION_TURN_STARTED:
        role = _role_from_source(command.source)
        if role is not None:
            await store.set_speaking_role(command.call_id, role)
    elif command.event_type is EventType.CONVERSATION_TURN_ENDED:
        await store.set_speaking_role(command.call_id, None)
    elif command.event_type is EventType.CONVERSATION_INTERRUPTION_DETECTED:
        await store.mark_interruption(command.call_id, command.timestamp)


def _role_from_source(source: Source) -> str | None:
    if source is Source.AGENT:
        return "agent"
    if source is Source.USER:
        return "user"
    return None


def _encode(snapshot: ActiveSessionSnapshot) -> str:
    return json.dumps(
        {
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
    )


def _decode(value: bytes | str) -> ActiveSessionSnapshot:
    data = json.loads(value)
    last_interruption_at = data.get("last_interruption_at")
    return ActiveSessionSnapshot(
        session_id=data["session_id"],
        agent_id=UUID(data["agent_id"]),
        status=data["status"],
        started_at=datetime.fromisoformat(data["started_at"]),
        speaking_role=data.get("speaking_role"),
        last_interruption_at=(
            datetime.fromisoformat(last_interruption_at)
            if last_interruption_at is not None
            else None
        ),
    )
