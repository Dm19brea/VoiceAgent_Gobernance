"""M5.2 — Session detail + agent listing endpoints (spec S2, S6)."""

from datetime import UTC, datetime

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.agent import Agent
from src.domain.enums import EvaluationResult, EventType, Source
from src.domain.evaluation_report import EvaluationReport
from src.domain.session import Session
from src.infrastructure.repositories.governance_repository import SqlAlchemyGovernanceRepository

START = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)


async def _seed(db_session: AsyncSession) -> Agent:
    repo = SqlAlchemyGovernanceRepository(db_session)
    agent = Agent(name="Citas", objective="Confirmar", vapi_assistant_id="asst-q2")
    await repo.add_agent(agent)

    evaluated = Session.open("call-a", agent.agent_id, START)
    evaluated.record(EventType.SESSION_STARTED, Source.PLATFORM, START, {})
    evaluated.record(EventType.CONVERSATION_AGENT_RESPONSE, Source.AGENT, START, {})
    evaluated.record(EventType.CONVERSATION_USER_INPUT, Source.USER, START, {})
    await repo.save_session(evaluated)

    pending = Session.open("call-b", agent.agent_id, START)
    pending.record(EventType.SESSION_STARTED, Source.PLATFORM, START, {})
    await repo.save_session(pending)

    await repo.add_report(
        EvaluationReport(
            session_id="call-a",
            score_global=80,
            result=EvaluationResult.PASSED,
            score_technical=80,
        )
    )
    await db_session.commit()
    return agent


async def test_get_session_returns_state_and_counters(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed(db_session)

    response = await client.get("/sessions/call-a")

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == "call-a"
    assert body["total_turns"] == 2
    assert body["agent_turns"] == 1
    assert body["user_turns"] == 1


async def test_get_unknown_session_returns_404(client: AsyncClient) -> None:
    response = await client.get("/sessions/missing")

    assert response.status_code == 404


async def test_list_agent_sessions_includes_results_and_pending(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    agent = await _seed(db_session)

    response = await client.get(f"/agents/{agent.agent_id}/sessions")

    assert response.status_code == 200
    by_id = {s["session_id"]: s for s in response.json()}
    assert by_id["call-a"]["result"] == "passed"
    assert by_id["call-a"]["score_global"] == 80
    assert by_id["call-b"]["result"] == "pending"
    assert by_id["call-b"]["score_global"] is None


async def test_list_agent_sessions_filters_by_result(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    agent = await _seed(db_session)

    response = await client.get(f"/agents/{agent.agent_id}/sessions", params={"result": "passed"})

    assert response.status_code == 200
    assert {s["session_id"] for s in response.json()} == {"call-a"}


async def test_list_agent_sessions_paginates(client: AsyncClient, db_session: AsyncSession) -> None:
    agent = await _seed(db_session)

    response = await client.get(f"/agents/{agent.agent_id}/sessions", params={"limit": 1})

    assert response.status_code == 200
    assert len(response.json()) == 1
