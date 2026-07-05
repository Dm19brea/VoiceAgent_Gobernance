"""M5.1 — GovernanceQuery read adapter (design D1/D2, spec S1, S6)."""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.agent import Agent
from src.domain.enums import EvaluationResult, EventType, Source
from src.domain.evaluation_report import EvaluationReport
from src.domain.session import Session
from src.infrastructure.repositories.governance_query import SqlAlchemyGovernanceQuery
from src.infrastructure.repositories.governance_repository import SqlAlchemyGovernanceRepository

START = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)


async def _seed(db_session: AsyncSession) -> Agent:
    repo = SqlAlchemyGovernanceRepository(db_session)
    agent = Agent(name="Citas", objective="Confirmar", vapi_assistant_id="asst-q")
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


async def test_get_session_returns_session_with_events(db_session: AsyncSession) -> None:
    await _seed(db_session)
    query = SqlAlchemyGovernanceQuery(db_session)

    session = await query.get_session("call-a")

    assert session is not None
    assert len(session.events) == 3


async def test_get_session_unknown_returns_none(db_session: AsyncSession) -> None:
    query = SqlAlchemyGovernanceQuery(db_session)

    assert await query.get_session("missing") is None


async def test_get_events_filters_by_source(db_session: AsyncSession) -> None:
    await _seed(db_session)
    query = SqlAlchemyGovernanceQuery(db_session)

    events = await query.get_events("call-a", source=Source.AGENT)

    assert len(events) == 1
    assert all(event.source is Source.AGENT for event in events)


async def test_get_events_filters_by_type(db_session: AsyncSession) -> None:
    await _seed(db_session)
    query = SqlAlchemyGovernanceQuery(db_session)

    events = await query.get_events("call-a", event_type=EventType.SESSION_STARTED)

    assert [event.event_type for event in events] == [EventType.SESSION_STARTED]


async def test_get_report_and_evidences_reads(db_session: AsyncSession) -> None:
    await _seed(db_session)
    query = SqlAlchemyGovernanceQuery(db_session)

    report = await query.get_report("call-a")
    assert report is not None
    assert report.result is EvaluationResult.PASSED
    assert await query.get_report("call-b") is None


async def test_list_agent_sessions_reports_results_and_pending(db_session: AsyncSession) -> None:
    agent = await _seed(db_session)
    query = SqlAlchemyGovernanceQuery(db_session)

    summaries = {s.session_id: s for s in await query.list_agent_sessions(agent.agent_id)}

    assert summaries["call-a"].result is EvaluationResult.PASSED
    assert summaries["call-a"].score_global == 80
    assert summaries["call-b"].result is None  # unevaluated -> pending
    assert summaries["call-b"].score_global is None


async def test_list_agent_sessions_filters_by_result(db_session: AsyncSession) -> None:
    agent = await _seed(db_session)
    query = SqlAlchemyGovernanceQuery(db_session)

    passed = await query.list_agent_sessions(agent.agent_id, result=EvaluationResult.PASSED)

    assert {s.session_id for s in passed} == {"call-a"}


async def test_list_agent_sessions_paginates(db_session: AsyncSession) -> None:
    agent = await _seed(db_session)
    query = SqlAlchemyGovernanceQuery(db_session)

    first_page = await query.list_agent_sessions(agent.agent_id, limit=1, offset=0)

    assert len(first_page) == 1
