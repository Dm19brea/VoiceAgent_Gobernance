# ruff: noqa: E402

import os
from collections.abc import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# This must run before application imports; tests never load developer secrets.
os.environ["GOVERNANCE_DISABLE_DOTENV"] = "1"

from src.adapters.rest.agent_routes import get_assistant_directory
from src.adapters.rest.auth import require_auth
from src.domain.agent import Agent
from src.infrastructure.config import settings
from src.infrastructure.db.base import Base
from src.infrastructure.db.models import (
    AgentModel,
    EvaluationReportModel,
    EventModel,
    EvidenceModel,
    RawEvent,
    SessionModel,
)
from src.infrastructure.db.session import get_session
from src.infrastructure.repositories.governance_repository import SqlAlchemyGovernanceRepository
from src.main import app
from tests.fakes import FakeAssistantDirectory

VAPI_WEBHOOK_SECRET = "test-vapi-webhook-secret"
VAPI_WEBHOOK_HEADERS = {"x-vapi-secret": VAPI_WEBHOOK_SECRET}


@pytest.fixture(autouse=True)
def _offline_assistant_directory() -> Generator[None, None, None]:
    """Keep Vapi assistant verification offline in every test.

    Defaults to "assistant exists" so existing ``POST /agents`` tests keep
    passing without the real Vapi API ever being reachable in the test
    process. Tests exercising S2/S3 override this dependency per-test.
    """
    app.dependency_overrides[get_assistant_directory] = lambda: FakeAssistantDirectory(exists=True)
    yield
    app.dependency_overrides.pop(get_assistant_directory, None)


@pytest.fixture(autouse=True)
def _bypass_dashboard_auth() -> Generator[None, None, None]:
    """Bypass JWT auth by default in every test (S2).

    Tests exercising the auth guard itself (`tests/test_auth.py`) pop this
    override per-test to exercise the real anonymous/valid-token paths.
    """
    app.dependency_overrides[require_auth] = lambda: "test-user"
    yield
    app.dependency_overrides.pop(require_auth, None)


@pytest.fixture(autouse=True)
def _configure_vapi_webhook_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configure the secret that legitimate webhook callers must send."""
    monkeypatch.setattr(settings, "vapi_webhook_secret", VAPI_WEBHOOK_SECRET)


@pytest.fixture(autouse=True)
def _offline_conversation_judge(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the post-terminal LLM judge offline in every test.

    The real ``OpenRouterConversationJudge`` short-circuits to ``None`` when no
    API key is configured. A developer ``.env`` leaks a real key into the test
    process, so any test that drives ``build_session_evidences_async`` without
    stubbing the judge would make live HTTP calls with retry backoff — slow and
    non-deterministic. Forcing an empty key on the shared settings singleton
    keeps the signal step deterministic and network-free. Judge-adapter tests
    pass their own explicit ``config``/``client`` and are unaffected.
    """
    monkeypatch.setattr(settings, "openrouter_api_key", "")


async def _clean(conn: AsyncConnection) -> None:
    # FK order: reports/evidences/events -> sessions -> agents; raw_events is independent.
    await conn.execute(delete(EvaluationReportModel))
    await conn.execute(delete(EvidenceModel))
    await conn.execute(delete(EventModel))
    await conn.execute(delete(SessionModel))
    await conn.execute(delete(AgentModel))
    await conn.execute(delete(RawEvent))


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Async session against the test database, with a clean schema per test."""
    engine = create_async_engine(settings.async_database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _clean(conn)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session

    async with engine.begin() as conn:
        await _clean(conn)
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """HTTP client whose requests use the test DB session."""

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def insert_governed_agent(
    db_session: AsyncSession, vapi_assistant_id: str, *, name: str | None = None
) -> Agent:
    """Insert a registered, non-deleted agent for webhook/ingestion tests (R3).

    Webhook ingestion now discards any call whose ``assistantId`` does not
    resolve to a governed (registered, non-deleted) agent, so tests exercising
    the governed path must register the agent up front instead of relying on
    the removed ingestion auto-provisioning.
    """
    repository = SqlAlchemyGovernanceRepository(db_session)
    agent = await repository.upsert_agent(
        Agent(
            name=name or f"Agent {vapi_assistant_id}",
            objective="test objective",
            vapi_assistant_id=vapi_assistant_id,
        )
    )
    await db_session.commit()
    return agent
