"""M5.4 — RedisActiveSessionStore round-trip against real Redis (spec S7)."""

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
