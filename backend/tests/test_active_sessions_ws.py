"""M5.5 — WebSocket supervision of active sessions (spec S10, S2 auth)."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from src.adapters.rest.auth import issue_token
from src.application.ports.active_sessions import ActiveSessionSnapshot
from src.infrastructure.config import settings
from src.main import app


def _valid_token(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(settings, "jwt_secret", "test-ws-jwt-secret")
    return issue_token("test-user")


class _FakeStore:
    def __init__(self, snapshots: list[ActiveSessionSnapshot]) -> None:
        self._snapshots = snapshots

    async def mark_active(self, snapshot: ActiveSessionSnapshot) -> None: ...

    async def mark_ended(self, session_id: str) -> None: ...

    async def list_active(self) -> list[ActiveSessionSnapshot]:
        return self._snapshots


def test_ws_sends_active_sessions_on_connect(monkeypatch: pytest.MonkeyPatch) -> None:
    snapshot = ActiveSessionSnapshot(
        session_id="s1",
        agent_id=uuid4(),
        status="active",
        started_at=datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC),
    )
    monkeypatch.setattr(
        "src.adapters.rest.ws.get_active_session_store", lambda: _FakeStore([snapshot])
    )
    monkeypatch.setattr("src.adapters.rest.ws.ACTIVE_SESSIONS_INTERVAL", 0.01)
    token = _valid_token(monkeypatch)

    client = TestClient(app)
    with client.websocket_connect(f"/ws/active-sessions?token={token}") as ws:
        data = ws.receive_json()

    assert isinstance(data, list)
    assert data[0]["session_id"] == "s1"
    assert data[0]["agent_id"] == str(snapshot.agent_id)
    assert data[0]["status"] == "active"


def test_ws_rejects_connection_without_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.adapters.rest.ws.ACTIVE_SESSIONS_INTERVAL", 0.01)

    client = TestClient(app)
    with (
        pytest.raises(WebSocketDisconnect) as exc_info,
        client.websocket_connect("/ws/active-sessions"),
    ):
        pass

    assert exc_info.value.code == 1008


def test_ws_rejects_connection_with_invalid_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "jwt_secret", "test-ws-jwt-secret")
    monkeypatch.setattr("src.adapters.rest.ws.ACTIVE_SESSIONS_INTERVAL", 0.01)

    client = TestClient(app)
    with (
        pytest.raises(WebSocketDisconnect) as exc_info,
        client.websocket_connect("/ws/active-sessions?token=not-a-real-token"),
    ):
        pass

    assert exc_info.value.code == 1008


def test_ws_serializes_speaking_role_and_interruption_when_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    interruption_at = datetime(2026, 1, 1, 10, 5, 0, tzinfo=UTC)
    snapshot = ActiveSessionSnapshot(
        session_id="s1",
        agent_id=uuid4(),
        status="active",
        started_at=datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC),
        speaking_role="agent",
        last_interruption_at=interruption_at,
    )
    monkeypatch.setattr(
        "src.adapters.rest.ws.get_active_session_store", lambda: _FakeStore([snapshot])
    )
    monkeypatch.setattr("src.adapters.rest.ws.ACTIVE_SESSIONS_INTERVAL", 0.01)
    token = _valid_token(monkeypatch)

    client = TestClient(app)
    with client.websocket_connect(f"/ws/active-sessions?token={token}") as ws:
        data = ws.receive_json()

    assert data[0]["speaking_role"] == "agent"
    assert data[0]["last_interruption_at"] == interruption_at.isoformat()


def test_ws_serializes_null_speaking_fields_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    snapshot = ActiveSessionSnapshot(
        session_id="s1",
        agent_id=uuid4(),
        status="active",
        started_at=datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC),
    )
    monkeypatch.setattr(
        "src.adapters.rest.ws.get_active_session_store", lambda: _FakeStore([snapshot])
    )
    monkeypatch.setattr("src.adapters.rest.ws.ACTIVE_SESSIONS_INTERVAL", 0.01)
    token = _valid_token(monkeypatch)

    client = TestClient(app)
    with client.websocket_connect(f"/ws/active-sessions?token={token}") as ws:
        data = ws.receive_json()

    assert data[0]["speaking_role"] is None
    assert data[0]["last_interruption_at"] is None
