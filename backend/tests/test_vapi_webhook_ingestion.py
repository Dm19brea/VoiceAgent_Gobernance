from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.db.models import EventModel, SessionModel


async def test_vapi_webhook_creates_session_and_event(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    payload: dict[str, Any] = {
        "message": {
            "type": "status-update",
            "status": "in-progress",
            "call": {"id": "call-w", "assistantId": "asst-w"},
        }
    }

    response = await client.post("/webhooks/vapi", json=payload)
    assert response.status_code == 200

    session_row = await db_session.scalar(
        select(SessionModel).where(SessionModel.session_id == "call-w")
    )
    assert session_row is not None

    events = (
        await db_session.scalars(select(EventModel).where(EventModel.session_id == "call-w"))
    ).all()
    assert len(events) == 1
    assert events[0].event_type == "session.started"
