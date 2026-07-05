"""M5.4 — Ingestion wires active-session state, best-effort (spec S8, S9)."""

from typing import Any

import pytest
from httpx import AsyncClient

from src.application.ports.active_sessions import ActiveSessionSnapshot


class _FakeStore:
    def __init__(self) -> None:
        self.active: dict[str, ActiveSessionSnapshot] = {}

    async def mark_active(self, snapshot: ActiveSessionSnapshot) -> None:
        self.active[snapshot.session_id] = snapshot

    async def mark_ended(self, session_id: str) -> None:
        self.active.pop(session_id, None)

    async def list_active(self) -> list[ActiveSessionSnapshot]:
        return list(self.active.values())


class _FailingStore:
    async def mark_active(self, snapshot: ActiveSessionSnapshot) -> None:
        raise RuntimeError("redis down")

    async def mark_ended(self, session_id: str) -> None:
        raise RuntimeError("redis down")

    async def list_active(self) -> list[ActiveSessionSnapshot]:
        raise RuntimeError("redis down")


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
