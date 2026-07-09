import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.application.use_cases.record_evaluation_triggered import RecordEvaluationTriggered
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

            evidences = build_evidences(governance_session)
            await repository.add_evidences(evidences)
            report = DeterministicEvaluator().evaluate(governance_session, evidences)
            await repository.add_report(report)
            await session.commit()
            return len(evidences)
    finally:
        await engine.dispose()


@celery_app.task(name="build_session_evidences")
def build_session_evidences(session_id: str) -> int:
    """Celery entrypoint: drives the async builder in its own event loop."""
    return asyncio.run(build_session_evidences_async(session_id))
