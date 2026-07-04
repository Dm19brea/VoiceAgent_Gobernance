from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from src.domain.enums import EventType, Source


@dataclass(frozen=True, slots=True)
class Event:
    """An atomic, immutable record within a session's governance trace."""

    session_id: str
    event_type: EventType
    source: Source
    sequence_number: int
    timestamp: datetime
    payload: dict[str, Any] = field(default_factory=dict)
    event_id: UUID = field(default_factory=uuid4)
