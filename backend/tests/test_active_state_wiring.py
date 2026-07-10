"""M5.4 — Ingestion wires active-session state, best-effort (spec S8, S9)."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient

from src.application.commands import IngestEventCommand
from src.application.ports.active_sessions import ActiveSessionSnapshot
from src.domain.enums import EventType, SessionStatus, Source
from src.domain.session import Session
from src.infrastructure.redis.active_sessions import update_active_state


class _FakeStore:
    def __init__(self) -> None:
        self.active: dict[str, ActiveSessionSnapshot] = {}
        self.speaking_role_calls: list[tuple[str, str | None]] = []
        self.interruption_calls: list[tuple[str, datetime]] = []
        self.list_active_call_count = 0

    async def mark_active(self, snapshot: ActiveSessionSnapshot) -> None:
        self.active[snapshot.session_id] = snapshot

    async def upsert_lifecycle(self, snapshot: ActiveSessionSnapshot) -> None:
        existing = self.active.get(snapshot.session_id)
        if existing is not None:
            snapshot = ActiveSessionSnapshot(
                session_id=snapshot.session_id,
                agent_id=snapshot.agent_id,
                status=snapshot.status,
                started_at=snapshot.started_at,
                speaking_role=existing.speaking_role,
                last_interruption_at=existing.last_interruption_at,
            )
        self.active[snapshot.session_id] = snapshot

    async def mark_ended(self, session_id: str) -> None:
        self.active.pop(session_id, None)

    async def list_active(self) -> list[ActiveSessionSnapshot]:
        self.list_active_call_count += 1
        return list(self.active.values())

    async def set_speaking_role(self, session_id: str, role: str | None) -> None:
        self.speaking_role_calls.append((session_id, role))

    async def mark_interruption(self, session_id: str, at: datetime) -> None:
        self.interruption_calls.append((session_id, at))


class _FailingStore:
    async def mark_active(self, snapshot: ActiveSessionSnapshot) -> None:
        raise RuntimeError("redis down")

    async def upsert_lifecycle(self, snapshot: ActiveSessionSnapshot) -> None:
        raise RuntimeError("redis down")

    async def mark_ended(self, session_id: str) -> None:
        raise RuntimeError("redis down")

    async def list_active(self) -> list[ActiveSessionSnapshot]:
        raise RuntimeError("redis down")

    async def set_speaking_role(self, session_id: str, role: str | None) -> None:
        raise RuntimeError("redis down")

    async def mark_interruption(self, session_id: str, at: datetime) -> None:
        raise RuntimeError("redis down")


class _FakeRepository:
    def __init__(self, session: Session | None = None) -> None:
        self._session = session

    async def get_session(self, session_id: str) -> Session | None:
        return self._session


def _command(event_type: EventType, source: Source) -> IngestEventCommand:
    return IngestEventCommand(
        call_id="call-a",
        assistant_id="asst-a",
        event_type=event_type,
        source=source,
        timestamp=datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC),
        payload={},
    )


async def test_turn_started_with_agent_source_sets_speaking_role_agent() -> None:
    store = _FakeStore()

    await update_active_state(
        store,
        repository=_FakeRepository(),
        command=_command(EventType.CONVERSATION_TURN_STARTED, Source.AGENT),
    )

    assert store.speaking_role_calls == [("call-a", "agent")]


async def test_turn_started_with_user_source_sets_speaking_role_user() -> None:
    store = _FakeStore()

    await update_active_state(
        store,
        repository=_FakeRepository(),
        command=_command(EventType.CONVERSATION_TURN_STARTED, Source.USER),
    )

    assert store.speaking_role_calls == [("call-a", "user")]


async def test_turn_ended_clears_speaking_role_regardless_of_source() -> None:
    store = _FakeStore()

    await update_active_state(
        store,
        repository=_FakeRepository(),
        command=_command(EventType.CONVERSATION_TURN_ENDED, Source.AGENT),
    )

    assert store.speaking_role_calls == [("call-a", None)]


async def test_interruption_detected_marks_interruption_and_leaves_speaking_role() -> None:
    store = _FakeStore()
    command = _command(EventType.CONVERSATION_INTERRUPTION_DETECTED, Source.USER)

    await update_active_state(store, repository=_FakeRepository(), command=command)

    assert store.interruption_calls == [("call-a", command.timestamp)]
    assert store.speaking_role_calls == []


async def test_duplicate_session_started_preserves_existing_speaking_state() -> None:
    """A resent status-update:in-progress must not wipe live speaking/interruption state."""
    store = _FakeStore()
    session = Session(
        session_id="call-a",
        agent_id=uuid4(),
        started_at=datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC),
        status=SessionStatus.ACTIVE,
    )
    repository = _FakeRepository(session)
    interruption_at = datetime(2026, 1, 1, 10, 5, 0, tzinfo=UTC)
    existing = ActiveSessionSnapshot(
        session_id="call-a",
        agent_id=session.agent_id,
        status="active",
        started_at=session.started_at,
        speaking_role="agent",
        last_interruption_at=interruption_at,
    )
    await store.mark_active(existing)

    await update_active_state(
        store,
        repository=repository,
        command=_command(EventType.SESSION_STARTED, Source.PLATFORM),
    )

    active = store.active["call-a"]
    assert active.speaking_role == "agent"
    assert active.last_interruption_at == interruption_at


async def test_duplicate_session_started_does_not_call_list_active() -> None:
    """SESSION_STARTED preservation must be O(1) atomic upsert, not a list_active() scan."""
    store = _FakeStore()
    session = Session(
        session_id="call-a",
        agent_id=uuid4(),
        started_at=datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC),
        status=SessionStatus.ACTIVE,
    )
    repository = _FakeRepository(session)
    await store.mark_active(
        ActiveSessionSnapshot(
            session_id="call-a",
            agent_id=session.agent_id,
            status="active",
            started_at=session.started_at,
            speaking_role="agent",
            last_interruption_at=None,
        )
    )

    await update_active_state(
        store,
        repository=repository,
        command=_command(EventType.SESSION_STARTED, Source.PLATFORM),
    )

    assert store.list_active_call_count == 0


async def test_first_session_started_marks_active_with_default_live_fields() -> None:
    store = _FakeStore()
    session = Session(
        session_id="call-a",
        agent_id=uuid4(),
        started_at=datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC),
        status=SessionStatus.ACTIVE,
    )
    repository = _FakeRepository(session)

    await update_active_state(
        store,
        repository=repository,
        command=_command(EventType.SESSION_STARTED, Source.PLATFORM),
    )

    active = store.active["call-a"]
    assert active.status == "active"
    assert active.speaking_role is None
    assert active.last_interruption_at is None


async def test_turn_started_with_unrecognized_source_does_not_clobber_speaking_role() -> None:
    """A TURN_STARTED with an unrecognized role must not reset speaking_role to None."""
    store = _FakeStore()

    await update_active_state(
        store,
        repository=_FakeRepository(),
        command=_command(EventType.CONVERSATION_TURN_STARTED, Source.PLATFORM),
    )

    assert store.speaking_role_calls == []


async def test_turn_ended_with_no_prior_turn_started_still_clears_cleanly() -> None:
    """No prior TURN_STARTED for this session; store no-ops safely (dropped turn_ended)."""
    store = _FakeStore()

    await update_active_state(
        store,
        repository=_FakeRepository(),
        command=_command(EventType.CONVERSATION_TURN_ENDED, Source.USER),
    )

    assert store.speaking_role_calls == [("call-a", None)]
    assert store.active == {}


def _payloads() -> tuple[dict[str, Any], dict[str, Any]]:
    call = {"id": "call-a", "assistantId": "asst-a"}
    started = {"message": {"type": "status-update", "status": "in-progress", "call": call}}
    ended = {"message": {"type": "end-of-call-report", "call": call}}
    return started, ended


async def test_ingestion_marks_session_active_then_ended(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _FakeStore()
    monkeypatch.setattr("src.adapters.rest.vapi.get_active_session_store", lambda: store)
    monkeypatch.setattr("src.adapters.rest.vapi.build_session_evidences", _NoopTask())
    started, ended = _payloads()

    await client.post("/webhooks/vapi", json=started)
    assert "call-a" in store.active
    assert store.active["call-a"].agent_id is not None

    await client.post("/webhooks/vapi", json=ended)
    assert "call-a" not in store.active


async def test_ingestion_marks_session_active_then_failed(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _FakeStore()
    monkeypatch.setattr("src.adapters.rest.vapi.get_active_session_store", lambda: store)
    monkeypatch.setattr("src.adapters.rest.vapi.build_session_evidences", _NoopTask())

    call = {"id": "call-b", "assistantId": "asst-b"}
    started = {"message": {"type": "status-update", "status": "in-progress", "call": call}}
    failed = {
        "message": {
            "type": "end-of-call-report",
            "endedReason": "pipeline-error-openai-llm-failed",
            "call": call,
        }
    }

    await client.post("/webhooks/vapi", json=started)
    assert "call-b" in store.active

    await client.post("/webhooks/vapi", json=failed)
    assert "call-b" not in store.active


async def test_ingestion_survives_a_redis_failure(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("src.adapters.rest.vapi.get_active_session_store", lambda: _FailingStore())
    started, _ = _payloads()

    response = await client.post("/webhooks/vapi", json=started)

    assert response.status_code == 200


class _NoopTask:
    def delay(self, session_id: str) -> None:
        pass
