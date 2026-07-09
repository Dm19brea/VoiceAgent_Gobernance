from datetime import datetime

from src.application.ports.governance_repository import GovernanceRepository
from src.domain.enums import EventType, Source
from src.domain.session import Session


class RecordEvaluationTriggered:
    """Append the post-terminal ``session.evaluation_triggered`` marker.

    Runs against an already-loaded, already-closed (ENDED/FAILED) session,
    right before evidence building starts. Idempotent by construction: the
    repository's marker-append is a no-op on conflict.
    """

    def __init__(self, repository: GovernanceRepository) -> None:
        self._repo = repository

    async def execute(self, session: Session, timestamp: datetime) -> None:
        event = session.append_marker(
            EventType.SESSION_EVALUATION_TRIGGERED, Source.PLATFORM, timestamp, {}
        )
        await self._repo.append_marker_event(event)
