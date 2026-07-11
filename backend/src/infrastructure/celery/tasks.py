import asyncio
import logging
from datetime import UTC, datetime
from time import perf_counter

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.adapters.llm.openrouter_judge import OpenRouterConversationJudge
from src.adapters.rest.vapi_mapping import (
    build_judge_transcript,
    derive_conversation_content,
    verdict_to_signal_commands,
)
from src.application.commands import ConversationContentCommand, SystemObservationCommand
from src.application.use_cases.record_conversation_content import RecordConversationContent
from src.application.use_cases.record_conversation_signals import RecordConversationSignals
from src.application.use_cases.record_evaluation_triggered import RecordEvaluationTriggered
from src.application.use_cases.record_system_observation import RecordSystemObservation
from src.domain.enums import EventType, Source
from src.domain.evaluation_report import EvaluationReport
from src.domain.event import Event
from src.domain.evidence_builder import build_evidences
from src.domain.scoring.evaluator import DeterministicEvaluator
from src.domain.session import Session
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
            await _record_conversation_content(session_id, governance_session)
            await _record_conversation_signals(session_id, governance_session)
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


_TERMINAL_EVENT_TYPES = frozenset({EventType.SESSION_ENDED, EventType.SESSION_FAILED})


def _terminal_event(governance_session: Session) -> Event | None:
    return next(
        (event for event in governance_session.events if event.event_type in _TERMINAL_EVENT_TYPES),
        None,
    )


async def _record_conversation_content(session_id: str, governance_session: Session) -> None:
    """Derive and persist conversation content events in an isolated best-effort transaction.

    Content is derived audit enrichment sourced from the session's own terminal
    event payload (the ``end-of-call-report`` message, retained with its
    ``artifact``). Isolated in its own engine/transaction after the evidence
    and evaluation observations, so a failure here never blocks or corrupts
    the critical path.
    """
    try:
        terminal_event = _terminal_event(governance_session)
        if terminal_event is None:
            return

        ended_at = governance_session.ended_at or terminal_event.timestamp
        derived = derive_conversation_content(terminal_event.payload, ended_at)
        if not derived:
            return

        commands = [
            ConversationContentCommand(
                session_id=session_id,
                event_type=event_type,
                source=source,
                timestamp=timestamp,
                role=role,
                content=content,
                turn_index=turn_index,
                payload=payload,
            )
            for event_type, source, timestamp, role, content, turn_index, payload in derived
        ]

        engine = create_async_engine(settings.async_database_url, poolclass=NullPool)
        try:
            maker = async_sessionmaker(engine, expire_on_commit=False)
            async with maker() as content_session:
                repository = SqlAlchemyGovernanceRepository(content_session)
                recorder = RecordConversationContent(repository)
                await recorder.execute(session_id, commands)
                await content_session.commit()
        finally:
            await engine.dispose()
    except Exception:
        logger.exception("Failed to record conversation content: session=%s", session_id)


async def _record_conversation_signals(session_id: str, governance_session: Session) -> None:
    """Run the LLM judge and persist derived signal events in an isolated best-effort transaction.

    Best-effort and isolated in its own engine/transaction, run AFTER conversation
    content derivation. A judge failure (network, retry exhaustion, or persistence
    error) never blocks or corrupts content derivation or the critical path.
    """
    try:
        terminal_event = _terminal_event(governance_session)
        if terminal_event is None:
            return

        transcript = build_judge_transcript(terminal_event.payload)
        if not transcript:
            return

        judge = OpenRouterConversationJudge()
        verdict = await judge.evaluate(transcript)
        if verdict is None:
            return

        ended_at = governance_session.ended_at or terminal_event.timestamp
        commands = verdict_to_signal_commands(verdict, session_id, ended_at)
        if not commands:
            return

        engine = create_async_engine(settings.async_database_url, poolclass=NullPool)
        try:
            maker = async_sessionmaker(engine, expire_on_commit=False)
            async with maker() as signal_session:
                repository = SqlAlchemyGovernanceRepository(signal_session)
                recorder = RecordConversationSignals(repository)
                await recorder.execute(session_id, commands)
                await signal_session.commit()
        finally:
            await engine.dispose()
    except Exception:
        logger.exception("Failed to record conversation signals: session=%s", session_id)
