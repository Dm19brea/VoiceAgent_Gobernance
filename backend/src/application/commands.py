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


@dataclass(frozen=True, slots=True)
class ConversationContentCommand:
    """A retry-safe post-terminal conversation content (agent/user turn) request.

    Identity is derived solely from ``role``, ``content`` (NFC-normalized,
    stripped) and ``turn_index`` — never from timestamps or raw delivery ids —
    so reprocessing the same report or a Vapi redelivery is a no-op.
    """

    session_id: str
    event_type: EventType
    source: Source
    timestamp: datetime
    role: str
    content: str
    turn_index: int
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ConversationSignalCommand:
    """A retry-safe post-terminal derived conversation signal.

    ``identity_fields`` intentionally contains only the stable outcome fields
    (topic count, goal verdict) — never ``reason`` text, timestamps, or raw
    delivery ids — so reprocessing the same report or a provider redelivery is
    a no-op.
    """

    session_id: str
    event_type: EventType
    source: Source
    timestamp: datetime
    identity_fields: dict[str, Any]
    payload: dict[str, Any]
