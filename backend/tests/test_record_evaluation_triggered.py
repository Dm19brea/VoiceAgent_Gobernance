from datetime import UTC, datetime
from uuid import uuid4

from src.application.use_cases.record_evaluation_triggered import RecordEvaluationTriggered
from src.domain.enums import EventType, Source
from src.domain.session import Session
from tests.fakes import InMemoryGovernanceRepository


async def test_record_evaluation_triggered_appends_marker_and_persists_it() -> None:
    session = Session.open(session_id="call-1", agent_id=uuid4(), started_at=datetime.now(UTC))
    session.record(EventType.SESSION_ENDED, Source.PLATFORM, datetime.now(UTC), {})
    repo = InMemoryGovernanceRepository()
    timestamp = datetime.now(UTC)

    await RecordEvaluationTriggered(repo).execute(session, timestamp)

    assert len(session.events) == 2
    appended_event = session.events[-1]
    assert appended_event.event_type is EventType.SESSION_EVALUATION_TRIGGERED
    assert appended_event.source is Source.PLATFORM
    assert appended_event.timestamp == timestamp
    assert appended_event.payload == {}

    assert repo.marker_events == [appended_event]
