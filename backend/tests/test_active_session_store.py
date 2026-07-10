"""M5.4 — RedisActiveSessionStore round-trip against real Redis (spec S7)."""

import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from uuid import uuid4

import pytest_asyncio
import redis.asyncio as redis

from src.application.ports.active_sessions import ActiveSessionSnapshot
from src.infrastructure.config import settings
from src.infrastructure.redis.active_sessions import RedisActiveSessionStore

TEST_KEY = "active_sessions:test"


@pytest_asyncio.fixture
async def store() -> AsyncGenerator[RedisActiveSessionStore, None]:
    client: redis.Redis = redis.from_url(settings.redis_url)
    await client.delete(TEST_KEY)
    yield RedisActiveSessionStore(client=client, key=TEST_KEY)
    await client.delete(TEST_KEY)
    await client.aclose()


def _snapshot(session_id: str) -> ActiveSessionSnapshot:
    return ActiveSessionSnapshot(
        session_id=session_id,
        agent_id=uuid4(),
        status="active",
        started_at=datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC),
    )


async def test_mark_active_then_list(store: RedisActiveSessionStore) -> None:
    snapshot = _snapshot("s1")

    await store.mark_active(snapshot)

    active = await store.list_active()
    assert len(active) == 1
    assert active[0].session_id == "s1"
    assert active[0].agent_id == snapshot.agent_id
    assert active[0].started_at == snapshot.started_at


async def test_mark_ended_removes_the_session(store: RedisActiveSessionStore) -> None:
    await store.mark_active(_snapshot("s1"))

    await store.mark_ended("s1")

    assert await store.list_active() == []


async def test_list_active_is_empty_by_default(store: RedisActiveSessionStore) -> None:
    assert await store.list_active() == []


async def test_decode_legacy_field_less_json_defaults_new_fields(
    store: RedisActiveSessionStore,
) -> None:
    """Snapshots written before this change lack the new fields (spec: backward-compatible)."""
    legacy_json = (
        '{"session_id": "s1", "agent_id": "'
        + str(uuid4())
        + '", "status": "active", "started_at": "2026-01-01T10:00:00+00:00"}'
    )
    await store._client.hset(store._key, "s1", legacy_json)

    active = await store.list_active()

    assert len(active) == 1
    assert active[0].speaking_role is None
    assert active[0].last_interruption_at is None


async def test_encode_decode_round_trip_with_speaking_fields(
    store: RedisActiveSessionStore,
) -> None:
    interruption_at = datetime(2026, 1, 1, 10, 5, 0, tzinfo=UTC)
    snapshot = ActiveSessionSnapshot(
        session_id="s1",
        agent_id=uuid4(),
        status="active",
        started_at=datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC),
        speaking_role="agent",
        last_interruption_at=interruption_at,
    )

    await store.mark_active(snapshot)

    active = await store.list_active()
    assert len(active) == 1
    assert active[0].speaking_role == "agent"
    assert active[0].last_interruption_at == interruption_at


async def test_set_speaking_role_merges_onto_existing_snapshot(
    store: RedisActiveSessionStore,
) -> None:
    await store.mark_active(_snapshot("s1"))

    await store.set_speaking_role("s1", "agent")

    active = await store.list_active()
    assert active[0].speaking_role == "agent"
    assert active[0].status == "active"
    assert active[0].session_id == "s1"


async def test_set_speaking_role_none_clears_it(store: RedisActiveSessionStore) -> None:
    await store.mark_active(_snapshot("s1"))
    await store.set_speaking_role("s1", "agent")

    await store.set_speaking_role("s1", None)

    active = await store.list_active()
    assert active[0].speaking_role is None


async def test_set_speaking_role_is_a_no_op_when_session_absent(
    store: RedisActiveSessionStore,
) -> None:
    await store.set_speaking_role("missing", "agent")

    assert await store.list_active() == []


async def test_mark_interruption_is_a_no_op_when_session_absent(
    store: RedisActiveSessionStore,
) -> None:
    await store.mark_interruption("missing", datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC))

    assert await store.list_active() == []


async def test_mark_interruption_sets_field_and_leaves_speaking_role_untouched(
    store: RedisActiveSessionStore,
) -> None:
    await store.mark_active(_snapshot("s1"))
    await store.set_speaking_role("s1", "agent")
    interruption_at = datetime(2026, 1, 1, 10, 5, 0, tzinfo=UTC)

    await store.mark_interruption("s1", interruption_at)

    active = await store.list_active()
    assert active[0].last_interruption_at == interruption_at
    assert active[0].speaking_role == "agent"


async def test_upsert_lifecycle_creates_with_default_live_fields_when_absent(
    store: RedisActiveSessionStore,
) -> None:
    snapshot = _snapshot("s1")

    await store.upsert_lifecycle(snapshot)

    active = await store.list_active()
    assert len(active) == 1
    assert active[0].session_id == "s1"
    assert active[0].speaking_role is None
    assert active[0].last_interruption_at is None


async def test_upsert_lifecycle_preserves_existing_live_fields(
    store: RedisActiveSessionStore,
) -> None:
    await store.mark_active(_snapshot("s1"))
    await store.set_speaking_role("s1", "agent")
    interruption_at = datetime(2026, 1, 1, 10, 5, 0, tzinfo=UTC)
    await store.mark_interruption("s1", interruption_at)

    await store.upsert_lifecycle(_snapshot("s1"))

    active = await store.list_active()
    assert active[0].speaking_role == "agent"
    assert active[0].last_interruption_at == interruption_at


async def test_upsert_lifecycle_is_atomic_under_concurrent_live_field_update(
    store: RedisActiveSessionStore,
) -> None:
    """A duplicate SESSION_STARTED concurrent with a TURN_STARTED/INTERRUPTION update on the
    same session must not lose the live-field update (same race class as the cross-field
    merge test below, applied to the SESSION_STARTED path).

    Atomicity here is guaranteed structurally: ``upsert_lifecycle`` runs as a single Redis
    ``EVAL`` (HGET -> mutate -> HSET happens server-side, inside the Lua script, in one
    round trip). Redis executes each EVAL to completion before starting the next, so no
    client-side interleave can be constructed to probe it — the read/modify/write never
    touches the Python client's ``hget``/``hset``, only the two calls to ``eval`` issued
    concurrently via ``asyncio.gather`` below. This test therefore verifies the observable
    outcome (both updates persist) rather than staging an artificial race.
    """
    await store.mark_active(_snapshot("s1"))
    interruption_at = datetime(2026, 1, 1, 10, 5, 0, tzinfo=UTC)

    await asyncio.gather(
        store.upsert_lifecycle(_snapshot("s1")),
        store.mark_interruption("s1", interruption_at),
    )

    active = await store.list_active()
    assert active[0].last_interruption_at == interruption_at


async def test_merge_is_atomic_under_concurrent_cross_field_updates(
    store: RedisActiveSessionStore,
) -> None:
    """Two concurrent webhooks updating different fields must not lose either update.

    Atomicity here is guaranteed structurally, not by staging a client-side interleave:
    ``_merge`` runs as a single Redis ``EVAL`` (HGET -> mutate -> HSET happens server-side,
    inside the Lua script, in one round trip), and Redis executes each EVAL to completion
    before starting the next. There is no client-visible HGET to slow down, so a
    read-modify-write race can only be observed against an implementation that does the
    merge client-side (e.g. a Python HGET->decode->HSET version) — this test verifies the
    observable outcome (both fields persist) for the two calls to ``eval`` issued
    concurrently via ``asyncio.gather`` below.
    """
    await store.mark_active(_snapshot("s1"))
    interruption_at = datetime(2026, 1, 1, 10, 5, 0, tzinfo=UTC)

    await asyncio.gather(
        store.set_speaking_role("s1", "agent"),
        store.mark_interruption("s1", interruption_at),
    )

    active = await store.list_active()
    assert active[0].speaking_role == "agent"
    assert active[0].last_interruption_at == interruption_at
