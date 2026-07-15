from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.db.models import RawEvent
from tests.conftest import insert_governed_agent

# Simulated Vapi server-message webhook: everything is wrapped in "message"
# with a discriminating "type". A status-update in-progress marks a started call.
VAPI_STATUS_UPDATE: dict[str, Any] = {
    "message": {
        "type": "status-update",
        "status": "in-progress",
        "call": {"id": "vapi-call-123", "assistantId": "asst-raw"},
        "timestamp": 1719655500000,
    }
}


async def test_vapi_webhook_persists_raw_event(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await insert_governed_agent(db_session, "asst-raw")

    response = await client.post("/webhooks/vapi", json=VAPI_STATUS_UPDATE)

    # Vapi ignores any non-200 response.
    assert response.status_code == 200

    row = await db_session.scalar(select(RawEvent))
    assert row is not None
    assert row.event_type == "status-update"
    assert row.payload["message"]["call"]["id"] == "vapi-call-123"
