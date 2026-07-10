import asyncio
import logging
from datetime import UTC, datetime
from time import perf_counter

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.application.commands import SystemObservationCommand
from src.application.use_cases.record_evaluation_triggered import RecordEvaluationTriggered
from src.application.use_cases.record_system_observation import RecordSystemObservation
from src.domain.enums import EventType, Source
from src.domain.evaluation_report import EvaluationReport
from src.domain.evidence_builder import build_evidences
from src.domain.scoring.evaluator import DeterministicEvaluator
from src.infrastructure.celery.app import celery_app
from src.infrastructure.config import settings
from src.infrastructure.repositories.governance_repository import SqlAlchemyGovernanceRepository

logger = logging.getLogger(__name__)


async def build_session_evidences_async(session_id: str) -> int:
    """Load a session, build its evidences, evaluate it and persist both. Returns the count.

    Records the ``session.evaluation_triggered`` marker first, in its own commit, so it
    stays durable regardless of the evidence/scoring outcome (failure-closed) and a retry
    never duplicates it (idempotent via the repository's ON CONFLICT append). Evidences and
    the evaluation report are then written in the same run (evidences -> report, design D8).
    The report is replaced per session, so re-running stays idempotent. Uses its own
    short-lived engine (NullPool) so each Celery task run is isolated from other event loops.
    """
    engine = create_async_engine(settings.async_database_url, poolclass=NullPool)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            repository = SqlAlchemyGovernanceRepository(session)
            governance_session = await repository.get_session(session_id)
            if governance_session is None:
                return 0

            await RecordEvaluationTriggered(repository).execute(
                governance_session, datetime.now(UTC)
            )
            await session.commit()  # marker durable regardless of evidence outcome
            logger.info("session.evaluation_triggered recorded: session=%s", session_id)

            evaluation_started = perf_counter()
            started_at = datetime.now(UTC)
            try:
                evidences = build_evidences(governance_session)
                await repository.add_evidences(evidences)
                report = DeterministicEvaluator().evaluate(governance_session, evidences)
                await repository.add_report(report)
                await session.commit()
            except Exception as error:
                await session.rollback()
                await _record_recoverable_evaluation_error(session_id, error)
                raise

            completed_at = datetime.now(UTC)
            await _record_evaluation_observations(
                session_id,
                _evaluation_success_observations(
                    report=report,
                    started_at=started_at,
                    completed_at=completed_at,
                    duration_milliseconds=(perf_counter() - evaluation_started) * 1000,
                ),
            )
            return len(evidences)
    finally:
        await engine.dispose()


@celery_app.task(name="build_session_evidences")
def build_session_evidences(session_id: str) -> int:
    """Celery entrypoint: drives the async builder in its own event loop."""
    return asyncio.run(build_session_evidences_async(session_id))


def _evaluation_success_observations(
    *,
    report: EvaluationReport,
    started_at: datetime,
    completed_at: datetime,
    duration_milliseconds: float,
) -> list[SystemObservationCommand]:
    """Build retry-safe timing and accepted-finding observations for one evaluation."""
    report_id = str(report.report_id)
    observations = [
        SystemObservationCommand(
            session_id=report.session_id,
            event_type=EventType.SYSTEM_LATENCY_MEASURED,
            source=Source.SYSTEM,
            timestamp=completed_at,
            identity_fields={"operation": "evidence_evaluation"},
            raw_event_id=None,
            payload={
                "duration_milliseconds": duration_milliseconds,
                "operation": "evidence_evaluation",
                "started_at": started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
                "unit": "milliseconds",
                "report_id": report_id,
            },
        )
    ]
    for finding in report.blocking_flags:
        observations.append(
            SystemObservationCommand(
                session_id=report.session_id,
                event_type=EventType.SYSTEM_FLAG_RAISED,
                source=Source.PLATFORM,
                timestamp=completed_at,
                identity_fields={
                    "code": finding.code,
                    "operation": "evidence_evaluation",
                    "reason": finding.reason,
                },
                raw_event_id=None,
                payload={
                    "code": finding.code,
                    "reason": finding.reason,
                    "report_id": report_id,
                    "source_operation": "evidence_evaluation",
                },
            )
        )
    return observations


async def _record_recoverable_evaluation_error(session_id: str, error: Exception) -> None:
    """Best-effort error observation that never recursively records its own failure."""
    await _record_evaluation_observations(
        session_id,
        [
            SystemObservationCommand(
                session_id=session_id,
                event_type=EventType.SYSTEM_ERROR,
                source=Source.SYSTEM,
                timestamp=datetime.now(UTC),
                identity_fields={
                    "error_type": type(error).__name__,
                    "operation": "evidence_evaluation",
                },
                raw_event_id=None,
                payload={
                    "classification": "recoverable_evaluation_failure",
                    "error_type": type(error).__name__,
                    "operation": "evidence_evaluation",
                    "reason": str(error),
                },
            )
        ],
    )


async def _record_evaluation_observations(
    session_id: str, observations: list[SystemObservationCommand]
) -> None:
    """Persist evaluation observations in an isolated best-effort transaction."""
    try:
        engine = create_async_engine(settings.async_database_url, poolclass=NullPool)
        try:
            maker = async_sessionmaker(engine, expire_on_commit=False)
            async with maker() as observation_session:
                repository = SqlAlchemyGovernanceRepository(observation_session)
                recorder = RecordSystemObservation(repository)
                for observation in observations:
                    await recorder.execute(observation)
                await observation_session.commit()
        finally:
            await engine.dispose()
    except Exception:
        logger.exception("Failed to record evaluation system observations: session=%s", session_id)
