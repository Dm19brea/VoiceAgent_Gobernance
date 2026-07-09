from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from src.domain.enums import EventType, Source


@dataclass(frozen=True, slots=True)
class IngestEventCommand:
    """A canonical event ready to be ingested, independent of any provider."""

    call_id: str
    assistant_id: str
    event_type: EventType
    source: Source
    timestamp: datetime
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class SystemObservationCommand:
    """A retry-safe post-terminal system observation request.

    ``identity_fields`` intentionally contains only stable, caller-selected
    values. Provider delivery timestamps and raw event UUIDs are provenance,
    never deduplication input.
    """

    session_id: str
    event_type: EventType
    source: Source
    timestamp: datetime
    identity_fields: dict[str, Any] | None
    raw_event_id: UUID | None
    payload: dict[str, Any]
