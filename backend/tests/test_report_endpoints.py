"""M5.3 — Report, evidences and events endpoints (spec S3, S4, S5)."""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.agent import Agent
from src.domain.enums import EvaluationResult, EventType, Source
from src.domain.evaluation_report import EvaluationReport
from src.domain.evidence_builder import build_evidences
from src.domain.session import Session
from src.infrastructure.repositories.governance_repository import SqlAlchemyGovernanceRepository

START = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
END = START + timedelta(seconds=47)


async def _seed(db_session: AsyncSession, *, with_report: bool = True) -> Agent:
    repo = SqlAlchemyGovernanceRepository(db_session)
    agent = Agent(name="Citas", objective="Confirmar", vapi_assistant_id="asst-q3")
    await repo.add_agent(agent)

    session = Session.open("call-a", agent.agent_id, START)
    session.record(EventType.SESSION_STARTED, Source.PLATFORM, START, {})
    session.record(EventType.CONVERSATION_AGENT_RESPONSE, Source.AGENT, START, {})
    session.record(EventType.CONVERSATION_USER_INPUT, Source.USER, START, {})
    session.record(
        EventType.SESSION_ENDED, Source.PLATFORM, END, {"report": {"ended_reason": "ok"}}
    )
    await repo.save_session(session)
    await repo.add_evidences(build_evidences(session))

    if with_report:
        await repo.add_report(
            EvaluationReport(
                session_id="call-a",
                score_global=81.4,
                result=EvaluationResult.PASSED,
                score_conversational=88.0,
                score_technical=74.0,
                score_risk=70.0,
            )
        )
    await db_session.commit()
    return agent


async def test_get_report_returns_nested_scores(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed(db_session)

    response = await client.get("/sessions/call-a/report")

    assert response.status_code == 200
    body = response.json()
    assert body["score_global"] == 81.4
    assert body["result"] == "passed"
    assert body["scores"]["conversational"] == 88.0
    assert body["scores"]["technical"] == 74.0
    assert body["scores"]["operational"] is None


async def test_get_report_404_when_not_evaluated(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed(db_session, with_report=False)

    response = await client.get("/sessions/call-a/report")

    assert response.status_code == 404


async def test_get_evidences_returns_the_session_evidences(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed(db_session)

    response = await client.get("/sessions/call-a/evidences")

    assert response.status_code == 200
    criteria = {e["criterion"] for e in response.json()}
    assert "total_turns" in criteria
    assert "session_completed" in criteria


async def test_get_events_filters_by_source(client: AsyncClient, db_session: AsyncSession) -> None:
    await _seed(db_session)

    response = await client.get("/sessions/call-a/events", params={"source": "agent"})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["source"] == "agent"


async def test_get_events_returns_trace_in_order(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed(db_session)

    response = await client.get("/sessions/call-a/events")

    assert response.status_code == 200
    sequence = [e["sequence_number"] for e in response.json()]
    assert sequence == sorted(sequence)
