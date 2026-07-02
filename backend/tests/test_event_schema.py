import uuid
from datetime import datetime
from typing import Any

import pytest
from pydantic import ValidationError

from src.adapters.rest.schemas import EventIn

VALID_EVENT: dict[str, Any] = {
    "event_type": "call.started",
    "agent_id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp": "2026-06-29T10:05:00Z",
    "source": "agent",
}


def test_event_in_accepts_valid_call_started() -> None:
    event = EventIn.model_validate(VALID_EVENT)

    assert event.event_type == "call.started"
    assert isinstance(event.agent_id, uuid.UUID)
    assert isinstance(event.timestamp, datetime)
    assert event.payload == {}


def test_event_in_rejects_missing_agent_id() -> None:
    payload = {k: v for k, v in VALID_EVENT.items() if k != "agent_id"}

    with pytest.raises(ValidationError):
        EventIn.model_validate(payload)


def test_event_in_rejects_invalid_agent_id() -> None:
    payload = {**VALID_EVENT, "agent_id": "not-a-uuid"}

    with pytest.raises(ValidationError):
        EventIn.model_validate(payload)


def test_event_in_rejects_empty_event_type() -> None:
    payload = {**VALID_EVENT, "event_type": ""}

    with pytest.raises(ValidationError):
        EventIn.model_validate(payload)
