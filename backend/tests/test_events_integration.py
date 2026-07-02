from typing import Any

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.db.models import RawEvent

VALID_EVENT: dict[str, Any] = {
    "event_type": "call.started",
    "agent_id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp": "2026-06-29T10:05:00Z",
    "source": "agent",
}


async def test_post_events_persists_raw_event(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    response = await client.post("/events", json=VALID_EVENT)

    assert response.status_code == 202

    count = await db_session.scalar(select(func.count()).select_from(RawEvent))
    assert count == 1

    row = await db_session.scalar(select(RawEvent))
    assert row is not None
    assert row.event_type == "call.started"
    assert row.payload["agent_id"] == "550e8400-e29b-41d4-a716-446655440000"
