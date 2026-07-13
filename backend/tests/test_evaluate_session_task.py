"""M4.6 — Celery task persists an EvaluationReport after evidences (design D8, spec S6)."""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.agent import Agent
from src.domain.enums import EvaluationResult, EventType, Source
from src.domain.session import Session
from src.infrastructure.celery.tasks import build_session_evidences_async
from src.infrastructure.db.models import EvaluationReportModel
from src.infrastructure.repositories.governance_repository import SqlAlchemyGovernanceRepository

START = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
END = datetime(2026, 1, 1, 10, 0, 47, tzinfo=UTC)


async def _persist_closed_session(
    repo: SqlAlchemyGovernanceRepository, session_id: str, db_session: AsyncSession
) -> None:
    agent = Agent(name="Citas", objective="Confirmar", vapi_assistant_id="asst-t9")
    await repo.add_agent(agent)
    session = Session.open(session_id, agent.agent_id, START)
    session.record(EventType.SESSION_STARTED, Source.PLATFORM, START, {})
    session.record(EventType.CONVERSATION_AGENT_RESPONSE, Source.AGENT, START, {})
    session.record(EventType.CONVERSATION_USER_INPUT, Source.USER, START, {})
    session.record(EventType.CONVERSATION_GOAL_ACHIEVED, Source.SYSTEM, START, {})
    session.record(
        EventType.SESSION_ENDED,
        Source.PLATFORM,
        END,
        {"report": {"ended_reason": "customer-ended-call"}},
    )
    await repo.save_session(session)
    await db_session.commit()


async def test_task_persists_a_deterministic_report(db_session: AsyncSession) -> None:
    repo = SqlAlchemyGovernanceRepository(db_session)
    await _persist_closed_session(repo, "call-t9", db_session)

    await build_session_evidences_async("call-t9")

    report = await repo.get_report_by_session("call-t9")
    assert report is not None
    assert report.session_id == "call-t9"
    assert report.result is EvaluationResult.PASSED
    codes = {m.code for m in report.metrics}
    assert {"engagement", "duration", "M-C01", "M-C02", "M-C03", "M-T03", "M-T04"}.issubset(codes)
    assert "completion" not in codes
    assert "clean_ending" not in codes
    assert report.score_global >= 75


async def test_task_replaces_the_report_on_re_run(db_session: AsyncSession) -> None:
    repo = SqlAlchemyGovernanceRepository(db_session)
    await _persist_closed_session(repo, "call-t9", db_session)

    await build_session_evidences_async("call-t9")
    await build_session_evidences_async("call-t9")

    count = await db_session.scalar(
        select(func.count())
        .select_from(EvaluationReportModel)
        .where(EvaluationReportModel.session_id == "call-t9")
    )
    assert count == 1


async def test_task_on_unknown_session_persists_no_report(db_session: AsyncSession) -> None:
    repo = SqlAlchemyGovernanceRepository(db_session)

    await build_session_evidences_async("does-not-exist")

    assert await repo.get_report_by_session("does-not-exist") is None
