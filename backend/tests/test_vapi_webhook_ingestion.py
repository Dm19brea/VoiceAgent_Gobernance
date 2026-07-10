from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.db.models import EventModel, RawEvent, SessionModel


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
    assert [event.event_type for event in events].count("session.failed") == 1
    errors = [event for event in events if event.event_type == "system.error"]
    assert len(errors) == 1
    assert errors[0].payload["reason"] == "pipeline-error-openai-llm-failed"


async def test_terminal_failure_redelivery_persists_one_correlated_error_and_one_lifecycle_event(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    call = {"id": "call-terminal-retry", "assistantId": "asst-terminal-retry"}
    started = {"message": {"type": "status-update", "status": "in-progress", "call": call}}
    failed = {
        "message": {
            "type": "end-of-call-report",
            "endedReason": "pipeline-error-openai-llm-failed",
            "durationSeconds": 12,
            "summary": "provider failure",
            "call": call,
        }
    }

    assert (await client.post("/webhooks/vapi", json=started)).status_code == 200
    assert (await client.post("/webhooks/vapi", json=failed)).status_code == 200
    assert (await client.post("/webhooks/vapi", json=failed)).status_code == 200

    events = (
        await db_session.scalars(
            select(EventModel)
            .where(EventModel.session_id == "call-terminal-retry")
            .order_by(EventModel.sequence_number)
        )
    ).all()
    assert [event.event_type for event in events].count("session.failed") == 1
    assert [event.event_type for event in events].count("system.error") == 1
    assert len((await db_session.scalars(select(RawEvent))).all()) == 3


async def test_terminal_observation_failure_rolls_back_raw_error_and_lifecycle(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.application.use_cases.record_system_observation import RecordSystemObservation

    call = {"id": "call-atomic", "assistantId": "asst-atomic"}
    started = {"message": {"type": "status-update", "status": "in-progress", "call": call}}
    failed = {
        "message": {
            "type": "end-of-call-report",
            "endedReason": "pipeline-error-openai-llm-failed",
            "call": call,
        }
    }
    assert (await client.post("/webhooks/vapi", json=started)).status_code == 200

    async def fail_observation(_: object, __: object) -> None:
        raise RuntimeError("injected observation insert failure")

    monkeypatch.setattr(RecordSystemObservation, "execute", fail_observation)

    with pytest.raises(RuntimeError, match="injected observation insert failure"):
        await client.post("/webhooks/vapi", json=failed)

    events = (
        await db_session.scalars(select(EventModel).where(EventModel.session_id == "call-atomic"))
    ).all()
    assert [event.event_type for event in events] == ["session.started"]
    raw_events = (await db_session.scalars(select(RawEvent))).all()
    assert len(raw_events) == 1


async def test_model_and_hang_remain_canonical_while_specialized_message_stays_raw_only(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    call = {"id": "call-regression", "assistantId": "asst-regression"}
    payloads = [
        {"message": {"type": "status-update", "status": "in-progress", "call": call}},
        {"message": {"type": "model-output", "output": "hello", "call": call}},
        {"message": {"type": "hang", "call": call}},
        {"message": {"type": "voice-request", "text": "do not promote", "call": call}},
    ]

    for payload in payloads:
        assert (await client.post("/webhooks/vapi", json=payload)).status_code == 200

    events = (
        await db_session.scalars(
            select(EventModel)
            .where(EventModel.session_id == "call-regression")
            .order_by(EventModel.sequence_number)
        )
    ).all()
    assert [event.event_type for event in events] == [
        "session.started",
        "system.model_invocation",
        "system.warning",
    ]
    assert len((await db_session.scalars(select(RawEvent))).all()) == 4


async def test_duplicate_transcript_threat_persists_one_normalized_flag(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    call = {"id": "call-threat", "assistantId": "asst-threat"}
    started = {"message": {"type": "status-update", "status": "in-progress", "call": call}}
    ended = {
        "message": {
            "type": "end-of-call-report",
            "endedReason": "customer-ended-call",
            "call": call,
        }
    }
    threat = {
        "message": {
            "type": "transcript",
            "transcriptType": "final",
            "transcript": "I will hurt you",
            "detectedThreats": [{"code": "violence", "reason": "Threat of harm"}],
            "call": call,
        }
    }

    for payload in [started, threat, threat]:
        assert (await client.post("/webhooks/vapi", json=payload)).status_code == 200

    session_row = await db_session.scalar(
        select(SessionModel).where(SessionModel.session_id == "call-threat")
    )
    assert session_row is not None
    assert session_row.status == "active"
    assert session_row.ended_at is None
    events = (
        await db_session.scalars(select(EventModel).where(EventModel.session_id == "call-threat"))
    ).all()
    flags = [event for event in events if event.event_type == "system.flag_raised"]
    assert len(flags) == 1
    assert flags[0].payload["code"] == "violence"
    assert len((await db_session.scalars(select(RawEvent))).all()) == 3

    assert (await client.post("/webhooks/vapi", json=ended)).status_code == 200


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
    assert [event.event_type for event in events].count("session.started") == 1
    assert [event.event_type for event in events].count("session.failed") == 1
    assert [event.event_type for event in events].count("system.error") == 1
