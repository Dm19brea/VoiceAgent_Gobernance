"""M5.5 — WebSocket supervision of active sessions (spec S10, S2 auth)."""

from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime
from uuid import uuid4

import bcrypt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.websockets import WebSocketDisconnect

from src.adapters.rest.auth import _issue_access_token, _issue_refresh_token
from src.application.ports.active_sessions import ActiveSessionSnapshot
from src.infrastructure.config import settings
from src.infrastructure.db.session import get_session
from src.infrastructure.repositories.credentials_repository import CredentialsRepository
from src.main import app
from tests.fakes import FAKE_LOGIN


class _FakeStore:
    def __init__(self, snapshots: list[ActiveSessionSnapshot]) -> None:
        self._snapshots = snapshots

    async def mark_active(self, snapshot: ActiveSessionSnapshot) -> None: ...

    async def mark_ended(self, session_id: str) -> None: ...

    async def list_active(self) -> list[ActiveSessionSnapshot]:
        return self._snapshots


@pytest.fixture
def _ws_get_session_override(db_session: AsyncSession) -> Generator[None, None, None]:
    """Override `get_session` for WS tests with a fresh cross-loop-safe engine.

    `TestClient` runs the app on its own event-loop thread, so the override
    must build a fresh `async_sessionmaker`/engine INSIDE the generator
    (created on the TestClient's loop) instead of reusing the pytest-asyncio
    `db_session` object, which is bound to a different event loop.
    """

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        engine = create_async_engine(settings.async_database_url)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            yield session
        await engine.dispose()

    app.dependency_overrides[get_session] = override_get_session
    yield
    app.dependency_overrides.pop(get_session, None)


async def _seed_credentials(db_session: AsyncSession) -> None:
    repository = CredentialsRepository(db_session)
    await repository.create(
        username="admin",
        password_hash=bcrypt.hashpw(FAKE_LOGIN.encode("utf-8"), bcrypt.gensalt()).decode("utf-8"),
        jwt_secret="test-ws-jwt-secret",
        vapi_webhook_secret="test-webhook-secret",
    )
    await db_session.commit()


class TestWebSocketAuth:
    """Real DB-backed access-token verification, BEFORE `accept()`."""

    async def test_valid_access_token_streams(
        self,
        db_session: AsyncSession,
        _ws_get_session_override: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        await _seed_credentials(db_session)
        row = await CredentialsRepository(db_session).get()
        assert row is not None
        token = _issue_access_token("admin", row.session_epoch, row.jwt_secret)

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

        client = TestClient(app)
        with client.websocket_connect(f"/ws/active-sessions?token={token}") as ws:
            data = ws.receive_json()

        assert isinstance(data, list)
        assert data[0]["session_id"] == "s1"
        assert data[0]["agent_id"] == str(snapshot.agent_id)
        assert data[0]["status"] == "active"

    async def test_missing_token_rejected(
        self, _ws_get_session_override: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("src.adapters.rest.ws.ACTIVE_SESSIONS_INTERVAL", 0.01)

        client = TestClient(app)
        with (
            pytest.raises(WebSocketDisconnect) as exc_info,
            client.websocket_connect("/ws/active-sessions") as connection,
        ):
            connection.receive_text()

        assert exc_info.value.code == 1008

    async def test_invalid_token_rejected(
        self, _ws_get_session_override: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("src.adapters.rest.ws.ACTIVE_SESSIONS_INTERVAL", 0.01)

        client = TestClient(app)
        with (
            pytest.raises(WebSocketDisconnect) as exc_info,
            client.websocket_connect("/ws/active-sessions?token=not-a-real-token") as connection,
        ):
            connection.receive_text()

        assert exc_info.value.code == 1008

    async def test_refresh_type_token_rejected(
        self,
        db_session: AsyncSession,
        _ws_get_session_override: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        await _seed_credentials(db_session)
        row = await CredentialsRepository(db_session).get()
        assert row is not None
        token = _issue_refresh_token("admin", row.session_epoch, row.jwt_secret)
        monkeypatch.setattr("src.adapters.rest.ws.ACTIVE_SESSIONS_INTERVAL", 0.01)

        client = TestClient(app)
        with (
            pytest.raises(WebSocketDisconnect) as exc_info,
            client.websocket_connect(f"/ws/active-sessions?token={token}") as connection,
        ):
            connection.receive_text()

        assert exc_info.value.code == 1008

    async def test_revoked_token_rejected(
        self,
        db_session: AsyncSession,
        _ws_get_session_override: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        await _seed_credentials(db_session)
        repository = CredentialsRepository(db_session)
        row = await repository.get()
        assert row is not None
        token = _issue_access_token("admin", row.session_epoch, row.jwt_secret)

        await repository.bump_epoch()
        await db_session.commit()

        monkeypatch.setattr("src.adapters.rest.ws.ACTIVE_SESSIONS_INTERVAL", 0.01)

        client = TestClient(app)
        with (
            pytest.raises(WebSocketDisconnect) as exc_info,
            client.websocket_connect(f"/ws/active-sessions?token={token}") as connection,
        ):
            connection.receive_text()

        assert exc_info.value.code == 1008


def test_ws_serializes_speaking_role_and_interruption_when_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.adapters.rest.ws import authenticate_ws

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
    app.dependency_overrides[authenticate_ws] = lambda: "test-user"

    client = TestClient(app)
    with client.websocket_connect("/ws/active-sessions?token=irrelevant") as ws:
        data = ws.receive_json()

    app.dependency_overrides.pop(authenticate_ws, None)

    assert data[0]["speaking_role"] == "agent"
    assert data[0]["last_interruption_at"] == interruption_at.isoformat()


def test_ws_serializes_null_speaking_fields_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.adapters.rest.ws import authenticate_ws

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
    app.dependency_overrides[authenticate_ws] = lambda: "test-user"

    client = TestClient(app)
    with client.websocket_connect("/ws/active-sessions?token=irrelevant") as ws:
        data = ws.receive_json()

    app.dependency_overrides.pop(authenticate_ws, None)

    assert data[0]["speaking_role"] is None
    assert data[0]["last_interruption_at"] is None
