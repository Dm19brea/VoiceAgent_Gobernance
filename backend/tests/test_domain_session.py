from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.domain.enums import EventType, SessionStatus, Source
from src.domain.exceptions import DomainError, SessionClosedError
from src.domain.session import Session


def _session() -> Session:
    return Session.open(session_id="call-1", agent_id=uuid4(), started_at=datetime.now(UTC))


def test_session_opens_active() -> None:
    session = _session()

    assert session.status is SessionStatus.ACTIVE
    assert session.ended_at is None


def test_record_assigns_increasing_sequence() -> None:
    session = _session()

    first = session.record(EventType.SESSION_STARTED, Source.PLATFORM, datetime.now(UTC), {})
    second = session.record(EventType.CONVERSATION_USER_INPUT, Source.USER, datetime.now(UTC), {})

    assert first.sequence_number == 1
    assert second.sequence_number == 2
    assert len(session.events) == 2


def test_session_ended_event_closes_session() -> None:
    session = _session()
    ended_at = datetime.now(UTC)

    session.record(EventType.SESSION_ENDED, Source.PLATFORM, ended_at, {})

    assert session.status is SessionStatus.ENDED
    assert session.ended_at == ended_at


def test_session_failed_event_fails_session() -> None:
    session = _session()
    failed_at = datetime.now(UTC)

    event = session.record(
        EventType.SESSION_FAILED,
        Source.PLATFORM,
        failed_at,
        {"reason": "timeout"},
    )

    assert event.event_type is EventType.SESSION_FAILED
    assert session.status is SessionStatus.FAILED
    assert session.ended_at == failed_at


def test_record_after_close_rejected() -> None:
    session = _session()
    session.record(EventType.SESSION_ENDED, Source.PLATFORM, datetime.now(UTC), {})

    with pytest.raises(SessionClosedError):
        session.record(EventType.CONVERSATION_USER_INPUT, Source.USER, datetime.now(UTC), {})


def test_record_after_failed_rejected() -> None:
    session = _session()
    session.record(EventType.SESSION_FAILED, Source.PLATFORM, datetime.now(UTC), {})

    with pytest.raises(SessionClosedError):
        session.record(EventType.CONVERSATION_USER_INPUT, Source.USER, datetime.now(UTC), {})


def test_append_marker_on_ended_session_continues_sequence_and_keeps_status() -> None:
    session = _session()
    ended_at = datetime.now(UTC)
    session.record(EventType.SESSION_STARTED, Source.PLATFORM, ended_at, {})
    session.record(EventType.SESSION_ENDED, Source.PLATFORM, ended_at, {})

    event = session.append_marker(
        EventType.SESSION_EVALUATION_TRIGGERED, Source.PLATFORM, datetime.now(UTC), {}
    )

    assert event.sequence_number == len(session.events)
    assert event.sequence_number == 3
    assert session.status is SessionStatus.ENDED
    assert session.ended_at == ended_at


def test_append_marker_on_failed_session_continues_sequence_and_keeps_status() -> None:
    session = _session()
    failed_at = datetime.now(UTC)
    session.record(EventType.SESSION_FAILED, Source.PLATFORM, failed_at, {})

    event = session.append_marker(
        EventType.SESSION_EVALUATION_TRIGGERED, Source.PLATFORM, datetime.now(UTC), {}
    )

    assert event.sequence_number == 2
    assert session.status is SessionStatus.FAILED
    assert session.ended_at == failed_at


def test_append_marker_on_active_session_rejected() -> None:
    session = _session()

    with pytest.raises(SessionClosedError):
        session.append_marker(
            EventType.SESSION_EVALUATION_TRIGGERED, Source.PLATFORM, datetime.now(UTC), {}
        )


def test_append_marker_rejects_non_marker_event_type() -> None:
    session = _session()
    session.record(EventType.SESSION_ENDED, Source.PLATFORM, datetime.now(UTC), {})

    with pytest.raises(DomainError):
        session.append_marker(EventType.SESSION_ENDED, Source.PLATFORM, datetime.now(UTC), {})


@pytest.mark.parametrize(
    "event_type",
    [
        EventType.SYSTEM_LATENCY_MEASURED,
        EventType.SYSTEM_ERROR,
        EventType.SYSTEM_FLAG_RAISED,
    ],
)
def test_append_system_observation_on_closed_session_keeps_lifecycle(
    event_type: EventType,
) -> None:
    session = _session()
    ended_at = datetime.now(UTC)
    session.record(EventType.SESSION_ENDED, Source.PLATFORM, ended_at, {})

    event = session.append_system_observation(event_type, Source.SYSTEM, datetime.now(UTC), {})

    assert event.event_type is event_type
    assert event.sequence_number == 2
    assert session.status is SessionStatus.ENDED
    assert session.ended_at == ended_at


def test_append_system_observation_rejects_non_system_observation_type() -> None:
    session = _session()
    session.record(EventType.SESSION_FAILED, Source.PLATFORM, datetime.now(UTC), {})

    with pytest.raises(DomainError):
        session.append_system_observation(
            EventType.SYSTEM_WARNING, Source.SYSTEM, datetime.now(UTC), {}
        )


def test_append_active_flag_observation_keeps_lifecycle_unchanged() -> None:
    session = _session()

    event = session.append_system_observation(
        EventType.SYSTEM_FLAG_RAISED, Source.SYSTEM, datetime.now(UTC), {}
    )

    assert event.event_type is EventType.SYSTEM_FLAG_RAISED
    assert session.status is SessionStatus.ACTIVE
    assert session.ended_at is None


def test_append_system_error_rejects_active_session() -> None:
    session = _session()

    with pytest.raises(SessionClosedError):
        session.append_system_observation(
            EventType.SYSTEM_ERROR, Source.SYSTEM, datetime.now(UTC), {}
        )


@pytest.mark.parametrize(
    "event_type",
    [
        EventType.CONVERSATION_AGENT_RESPONSE,
        EventType.CONVERSATION_USER_INPUT,
    ],
)
def test_append_conversation_content_on_closed_session_keeps_lifecycle(
    event_type: EventType,
) -> None:
    session = _session()
    ended_at = datetime.now(UTC)
    session.record(EventType.SESSION_ENDED, Source.PLATFORM, ended_at, {})

    event = session.append_conversation_content(event_type, Source.AGENT, datetime.now(UTC), {})

    assert event.event_type is event_type
    assert event.sequence_number == 2
    assert session.status is SessionStatus.ENDED
    assert session.ended_at == ended_at


def test_append_conversation_content_on_failed_session_keeps_lifecycle() -> None:
    session = _session()
    failed_at = datetime.now(UTC)
    session.record(EventType.SESSION_FAILED, Source.PLATFORM, failed_at, {})

    event = session.append_conversation_content(
        EventType.CONVERSATION_USER_INPUT, Source.USER, datetime.now(UTC), {}
    )

    assert event.sequence_number == 2
    assert session.status is SessionStatus.FAILED
    assert session.ended_at == failed_at


def test_append_conversation_content_rejects_active_session() -> None:
    session = _session()

    with pytest.raises(SessionClosedError):
        session.append_conversation_content(
            EventType.CONVERSATION_AGENT_RESPONSE, Source.AGENT, datetime.now(UTC), {}
        )


def test_append_conversation_content_rejects_non_content_event_type() -> None:
    session = _session()
    session.record(EventType.SESSION_ENDED, Source.PLATFORM, datetime.now(UTC), {})

    with pytest.raises(DomainError):
        session.append_conversation_content(
            EventType.SYSTEM_ERROR, Source.SYSTEM, datetime.now(UTC), {}
        )


def test_append_conversation_content_accepts_optional_event_id() -> None:
    session = _session()
    session.record(EventType.SESSION_ENDED, Source.PLATFORM, datetime.now(UTC), {})
    event_id = uuid4()

    event = session.append_conversation_content(
        EventType.CONVERSATION_USER_INPUT,
        Source.USER,
        datetime.now(UTC),
        {},
        event_id=event_id,
    )

    assert event.event_id == event_id
