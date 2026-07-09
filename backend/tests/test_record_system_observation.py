from datetime import UTC, datetime
from uuid import uuid4

from pytest import LogCaptureFixture

from src.application.commands import SystemObservationCommand
from src.application.use_cases.record_system_observation import (
    RecordSystemObservation,
    canonical_observation_event_id,
)
from src.domain.enums import EventType, SessionStatus, Source
from src.domain.session import Session
from tests.fakes import InMemoryGovernanceRepository


def _command(*, timestamp: datetime | None = None) -> SystemObservationCommand:
    return SystemObservationCommand(
        session_id="call-observation",
        event_type=EventType.SYSTEM_ERROR,
        source=Source.SYSTEM,
        timestamp=timestamp or datetime.now(UTC),
        identity_fields={"operation": "evidence_evaluation", "run_id": "run-1"},
        raw_event_id=uuid4(),
        payload={"classification": "recoverable", "reason": "timeout"},
    )


def test_canonical_observation_identity_is_timestamp_independent_and_input_specific() -> None:
    first = _command(timestamp=datetime(2026, 7, 9, 10, tzinfo=UTC))
    retry = _command(timestamp=datetime(2026, 7, 9, 11, tzinfo=UTC))
    distinct = SystemObservationCommand(
        session_id=first.session_id,
        event_type=first.event_type,
        source=first.source,
        timestamp=first.timestamp,
        identity_fields={"operation": "evidence_evaluation", "run_id": "run-2"},
        raw_event_id=first.raw_event_id,
        payload=first.payload,
    )

    assert canonical_observation_event_id(first) == canonical_observation_event_id(retry)
    assert canonical_observation_event_id(first) != canonical_observation_event_id(distinct)


async def test_record_system_observation_is_idempotent_and_preserves_closed_status() -> None:
    repo = InMemoryGovernanceRepository()
    session = Session.open("call-observation", uuid4(), datetime.now(UTC))
    ended_at = datetime.now(UTC)
    session.record(EventType.SESSION_ENDED, Source.PLATFORM, ended_at, {})
    await repo.save_session(session)
    use_case = RecordSystemObservation(repo)

    first = await use_case.execute(_command(timestamp=datetime(2026, 7, 9, 10, tzinfo=UTC)))
    retry = await use_case.execute(_command(timestamp=datetime(2026, 7, 9, 11, tzinfo=UTC)))

    assert first is not None
    assert retry == first
    assert first.event_type is EventType.SYSTEM_ERROR
    assert first.payload["identity"] == str(first.event_id)
    assert first.payload["raw_event_id"] is not None
    assert session.status is SessionStatus.ENDED
    assert session.ended_at == ended_at
    assert [event.event_type for event in session.events] == [
        EventType.SESSION_ENDED,
        EventType.SYSTEM_ERROR,
    ]


async def test_record_system_observation_logs_and_keeps_raw_only_without_stable_identity(
    caplog: LogCaptureFixture,
) -> None:
    repo = InMemoryGovernanceRepository()
    use_case = RecordSystemObservation(repo)
    command = SystemObservationCommand(
        session_id="call-observation",
        event_type=EventType.SYSTEM_FLAG_RAISED,
        source=Source.PLATFORM,
        timestamp=datetime.now(UTC),
        identity_fields=None,
        raw_event_id=uuid4(),
        payload={"code": "threat"},
    )

    result = await use_case.execute(command)

    assert result is None
    assert "stable identity" in caplog.text
