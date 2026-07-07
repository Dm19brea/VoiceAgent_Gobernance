from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.domain.enums import EventType, SessionStatus, Source
from src.domain.exceptions import SessionClosedError
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
