"""M6.1 — Global sessions listing + CORS (design D2, spec S2)."""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.agent import Agent
from src.domain.enums import EventType, Source
from src.domain.session import Session
from src.infrastructure.repositories.governance_repository import SqlAlchemyGovernanceRepository

START = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)


async def _seed(db_session: AsyncSession, count: int = 3) -> Agent:
    repo = SqlAlchemyGovernanceRepository(db_session)
    agent = Agent(name="Citas", objective="Confirmar", vapi_assistant_id="asst-m6")
    await repo.add_agent(agent)
    for i in range(count):
        session = Session.open(f"call-{i}", agent.agent_id, START + timedelta(minutes=i))
        session.record(EventType.SESSION_STARTED, Source.PLATFORM, START, {})
        await repo.save_session(session)
    await db_session.commit()
    return agent


async def test_list_sessions_returns_recent_sessions(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed(db_session, count=3)

    response = await client.get("/sessions")

    assert response.status_code == 200
    assert len(response.json()) == 3


async def test_list_sessions_paginates(client: AsyncClient, db_session: AsyncSession) -> None:
    await _seed(db_session, count=3)

    response = await client.get("/sessions", params={"limit": 2})

    assert response.status_code == 200
    assert len(response.json()) == 2


async def test_cors_headers_present_for_allowed_origin(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed(db_session, count=1)

    response = await client.get("/sessions", headers={"Origin": "http://localhost:3000"})

    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


async def test_list_sessions_exposes_agent_name(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed(db_session, count=1)

    response = await client.get("/sessions")

    assert response.status_code == 200
    assert response.json()[0]["agent_name"] == "Citas"


async def test_sessions_and_agent_sessions_share_shape(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    agent = await _seed(db_session, count=1)

    all_response = await client.get("/sessions")
    agent_response = await client.get(f"/agents/{agent.agent_id}/sessions")

    assert all_response.status_code == 200
    assert agent_response.status_code == 200
    all_item = all_response.json()[0]
    agent_item = agent_response.json()[0]
    assert set(all_item.keys()) == set(agent_item.keys())
    assert "agent_name" in all_item
    assert "agent_name" in agent_item
