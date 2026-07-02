from typing import Any

from httpx import AsyncClient
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

VALID_EVENT: dict[str, Any] = {
    "event_type": "call.started",
    "agent_id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp": "2026-06-29T10:05:00Z",
    "source": "agent",
}


async def test_ingest_emits_trace_logs(client: AsyncClient, db_session: AsyncSession) -> None:
    messages: list[str] = []
    sink_id = logger.add(messages.append, level="INFO", format="{message}")
    try:
        response = await client.post("/events", json=VALID_EVENT)
    finally:
        logger.remove(sink_id)

    assert response.status_code == 202
    assert any("call.started" in message for message in messages)
