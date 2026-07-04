import dataclasses
from datetime import UTC, datetime

import pytest

from src.domain.enums import EventType, Source
from src.domain.event import Event


def _event() -> Event:
    return Event(
        session_id="call-1",
        event_type=EventType.SESSION_STARTED,
        source=Source.PLATFORM,
        sequence_number=1,
        timestamp=datetime.now(UTC),
    )


def test_event_construction() -> None:
    event = _event()

    assert event.event_type is EventType.SESSION_STARTED
    assert event.sequence_number == 1
    assert event.payload == {}
    assert event.event_id is not None


def test_event_is_immutable() -> None:
    event = _event()

    with pytest.raises(dataclasses.FrozenInstanceError):
        event.sequence_number = 2  # type: ignore[misc]
