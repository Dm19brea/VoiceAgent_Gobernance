"""R3 — discard webhook calls for unknown/soft-deleted agents entirely (S12-S15)."""

from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.enums import AgentStatus
from src.infrastructure.db.models import AgentModel, EventModel, RawEvent, SessionModel
from src.infrastructure.repositories.governance_repository import SqlAlchemyGovernanceRepository
from tests.conftest import insert_governed_agent


def _call(call_id: str, assistant_id: str) -> dict[str, Any]:
    return {"id": call_id, "assistantId": assistant_id}


def _started(call: dict[str, Any]) -> dict[str, Any]:
    return {"message": {"type": "status-update", "status": "in-progress", "call": call}}


def _ended(call: dict[str, Any]) -> dict[str, Any]:
    return {"message": {"type": "end-of-call-report", "call": call}}


async def _assert_nothing_persisted(db_session: AsyncSession, call_id: str) -> None:
    assert (await db_session.scalar(select(RawEvent))) is None
    assert (
        await db_session.scalar(select(SessionModel).where(SessionModel.session_id == call_id))
    ) is None
    assert (
        await db_session.scalar(select(EventModel).where(EventModel.session_id == call_id))
    ) is None


async def test_unknown_assistant_webhook_is_ignored_and_persists_nothing(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """S12 — an assistant_id that was never registered discards the call."""
    call = _call("call-unknown", "asst-never-registered")

    response = await client.post("/webhooks/vapi", json=_started(call))

    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}
    await _assert_nothing_persisted(db_session, "call-unknown")
    assert (
        await db_session.scalar(
            select(AgentModel).where(AgentModel.vapi_assistant_id == "asst-never-registered")
        )
    ) is None


async def test_soft_deleted_assistant_webhook_is_ignored_and_stays_deleted(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """S13 — a soft-deleted assistant's webhook is discarded and the agent stays deleted."""
    agent = await insert_governed_agent(db_session, "asst-soft-deleted")
    repository = SqlAlchemyGovernanceRepository(db_session)
    await repository.soft_delete_agent(agent.agent_id, deleted_at=datetime.now(UTC))
    await db_session.commit()
    call = _call("call-deleted", "asst-soft-deleted")

    response = await client.post("/webhooks/vapi", json=_started(call))

    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}
    await _assert_nothing_persisted(db_session, "call-deleted")
    row = await db_session.scalar(
        select(AgentModel).where(AgentModel.vapi_assistant_id == "asst-soft-deleted")
    )
    assert row is not None
    assert row.deleted_at is not None


async def test_discarded_call_enqueues_no_celery_task(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S14 — a discarded terminal call must not enqueue evidence building."""
    calls: list[str] = []
    monkeypatch.setattr(
        "src.adapters.rest.vapi.build_session_evidences",
        type("_Fake", (), {"delay": staticmethod(lambda session_id: calls.append(session_id))}),
    )
    call = _call("call-discarded-celery", "asst-discarded-celery")

    await client.post("/webhooks/vapi", json=_ended(call))

    assert calls == []


async def test_discarded_call_writes_no_redis_active_session(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S14 — a discarded call must not write to the active-session store."""

    class _SpyStore:
        def __init__(self) -> None:
            self.mark_active_calls: list[str] = []

        async def mark_active(self, snapshot: object) -> None:
            self.mark_active_calls.append(getattr(snapshot, "session_id", ""))

        async def upsert_lifecycle(self, snapshot: object) -> None:
            self.mark_active_calls.append(getattr(snapshot, "session_id", ""))

        async def mark_ended(self, session_id: str) -> None:
            self.mark_active_calls.append(session_id)

    spy = _SpyStore()
    monkeypatch.setattr("src.adapters.rest.vapi.get_active_session_store", lambda: spy)
    call = _call("call-discarded-redis", "asst-discarded-redis")

    await client.post("/webhooks/vapi", json=_started(call))

    assert spy.mark_active_calls == []


async def test_discarded_call_records_no_latency_observation(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """S14 — a discarded terminal call must not record a webhook ingestion latency."""
    call = _call("call-discarded-latency", "asst-discarded-latency")

    await client.post("/webhooks/vapi", json=_ended(call))

    rows = (
        await db_session.scalars(
            select(EventModel).where(EventModel.event_type == "system.latency_measured")
        )
    ).all()
    assert rows == []


async def test_governed_and_discarded_traffic_never_creates_unregistered_agent(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """S15 — no webhook path ever creates an ``AgentStatus.UNREGISTERED`` agent."""
    await insert_governed_agent(db_session, "asst-governed-s15")
    governed_call = _call("call-governed-s15", "asst-governed-s15")
    unknown_call = _call("call-unknown-s15", "asst-unknown-s15")

    await client.post("/webhooks/vapi", json=_started(governed_call))
    await client.post("/webhooks/vapi", json=_started(unknown_call))

    rows = (
        await db_session.scalars(
            select(AgentModel).where(AgentModel.status == AgentStatus.UNREGISTERED.value)
        )
    ).all()
    assert rows == []
