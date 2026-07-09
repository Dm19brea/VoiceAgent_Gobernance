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


async def test_end_of_call_report_with_error_reason_fails_the_session(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    call = {"id": "call-f", "assistantId": "asst-f"}
    started = {"message": {"type": "status-update", "status": "in-progress", "call": call}}
    ended = {
        "message": {
            "type": "end-of-call-report",
            "endedReason": "pipeline-error-openai-llm-failed",
            "call": call,
        }
    }

    await client.post("/webhooks/vapi", json=started)
    response = await client.post("/webhooks/vapi", json=ended)
    assert response.status_code == 200

    session_row = await db_session.scalar(
        select(SessionModel).where(SessionModel.session_id == "call-f")
    )
    assert session_row is not None
    assert session_row.status == "failed"

    events = (
        await db_session.scalars(
            select(EventModel)
            .where(EventModel.session_id == "call-f")
            .order_by(EventModel.sequence_number)
        )
    ).all()
    assert [event.event_type for event in events] == ["session.started", "session.failed"]


async def test_second_terminal_event_after_failed_is_ignored(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    call = {"id": "call-g", "assistantId": "asst-g"}
    started = {"message": {"type": "status-update", "status": "in-progress", "call": call}}
    failed = {
        "message": {
            "type": "end-of-call-report",
            "endedReason": "pipeline-error-openai-llm-failed",
            "call": call,
        }
    }
    second = {
        "message": {
            "type": "end-of-call-report",
            "endedReason": "customer-ended-call",
            "call": call,
        }
    }

    await client.post("/webhooks/vapi", json=started)
    await client.post("/webhooks/vapi", json=failed)
    response = await client.post("/webhooks/vapi", json=second)
    assert response.status_code == 200

    session_row = await db_session.scalar(
        select(SessionModel).where(SessionModel.session_id == "call-g")
    )
    assert session_row is not None
    assert session_row.status == "failed"

    events = (
        await db_session.scalars(select(EventModel).where(EventModel.session_id == "call-g"))
    ).all()
    assert len(events) == 2
