"""M4.6 — Repository persistence for EvaluationReport (design D7, spec R8)."""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.agent import Agent
from src.domain.enums import Dimension, EvaluationResult
from src.domain.evaluation_report import EvaluationReport
from src.domain.scoring.flags import BlockingFlag
from src.domain.scoring.metric import Metric
from src.domain.session import Session
from src.infrastructure.db.models import EvaluationReportModel
from src.infrastructure.repositories.governance_repository import (
    SqlAlchemyGovernanceRepository,
)
from tests.fakes import InMemoryGovernanceRepository


async def _persist_session(
    repo: SqlAlchemyGovernanceRepository, session_id: str = "call-eval"
) -> None:
    agent = Agent(name="Citas", objective="Confirmar", vapi_assistant_id="asst-eval")
    await repo.add_agent(agent)
    await repo.save_session(Session.open(session_id, agent.agent_id, datetime.now(UTC)))


def _report(
    *,
    session_id: str = "call-eval",
    score: float = 82.0,
    result: EvaluationResult = EvaluationResult.PASSED,
) -> EvaluationReport:
    return EvaluationReport(
        session_id=session_id,
        score_global=score,
        result=result,
        score_technical=100,
        score_risk=50,
        blocking_flags=[BlockingFlag(code="session_not_completed", reason="No completion.")],
        metrics=[
            Metric(
                code="completion",
                dimension=Dimension.TECHNICAL,
                raw_value=1.0,
                normalized_score=100,
                weight=3.0,
                unit="bool",
            )
        ],
    )


async def test_add_and_get_report_round_trip(db_session: AsyncSession) -> None:
    repo = SqlAlchemyGovernanceRepository(db_session)
    await _persist_session(repo)
    report = _report()

    await repo.add_report(report)
    await db_session.commit()

    loaded = await repo.get_report_by_session("call-eval")
    assert loaded is not None
    assert loaded.report_id == report.report_id
    assert loaded.score_global == 82.0
    assert loaded.result is EvaluationResult.PASSED
    assert loaded.score_technical == 100
    assert loaded.score_conversational is None
    assert loaded.blocking_flags == report.blocking_flags
    assert loaded.metrics == report.metrics


async def test_get_report_for_unknown_session_returns_none(db_session: AsyncSession) -> None:
    repo = SqlAlchemyGovernanceRepository(db_session)

    assert await repo.get_report_by_session("missing") is None


async def test_add_report_replaces_previous_report_for_session(db_session: AsyncSession) -> None:
    repo = SqlAlchemyGovernanceRepository(db_session)
    await _persist_session(repo)

    await repo.add_report(_report(score=50.0, result=EvaluationResult.FAILED))
    await repo.add_report(_report(score=90.0, result=EvaluationResult.PASSED))
    await db_session.commit()

    count = await db_session.scalar(
        select(func.count())
        .select_from(EvaluationReportModel)
        .where(EvaluationReportModel.session_id == "call-eval")
    )
    assert count == 1

    loaded = await repo.get_report_by_session("call-eval")
    assert loaded is not None
    assert loaded.score_global == 90.0
    assert loaded.result is EvaluationResult.PASSED


async def test_fake_repository_stores_and_replaces_report() -> None:
    repo = InMemoryGovernanceRepository()

    await repo.add_report(_report(score=50.0, result=EvaluationResult.FAILED))
    await repo.add_report(_report(score=90.0, result=EvaluationResult.PASSED))

    loaded = await repo.get_report_by_session("call-eval")
    assert loaded is not None
    assert loaded.score_global == 90.0


async def test_fake_repository_returns_none_for_unknown_session() -> None:
    repo = InMemoryGovernanceRepository()

    assert await repo.get_report_by_session("missing") is None
