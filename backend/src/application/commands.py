from dataclasses import dataclass
from datetime import datetime
from typing import Any

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
