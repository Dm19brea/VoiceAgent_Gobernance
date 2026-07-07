from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from src.domain.enums import EventType, SessionStatus, Source
from src.domain.event import Event
from src.domain.exceptions import SessionClosedError


@dataclass
class Session:
    """Aggregate root for one governance session (= one Vapi call)."""

    session_id: str
    agent_id: UUID
    started_at: datetime
    status: SessionStatus = SessionStatus.ACTIVE
    ended_at: datetime | None = None
    events: list[Event] = field(default_factory=list)

    @classmethod
    def open(cls, session_id: str, agent_id: UUID, started_at: datetime) -> "Session":
        return cls(session_id=session_id, agent_id=agent_id, started_at=started_at)

    def record(
        self,
        event_type: EventType,
        source: Source,
        timestamp: datetime,
        payload: dict[str, Any],
    ) -> Event:
        """Append a new event, assigning the next sequence number.

        Closes the session when a terminal event is recorded. Rejects any event
        once the session is no longer active.
        """
        if self.status is not SessionStatus.ACTIVE:
            raise SessionClosedError(f"Session {self.session_id} is {self.status}")

        event = Event(
            session_id=self.session_id,
            event_type=event_type,
            source=source,
            sequence_number=len(self.events) + 1,
            timestamp=timestamp,
            payload=payload,
        )
        self.events.append(event)

        if event_type is EventType.SESSION_ENDED:
            self.status = SessionStatus.ENDED
            self.ended_at = timestamp
        elif event_type is EventType.SESSION_FAILED:
            self.status = SessionStatus.FAILED
            self.ended_at = timestamp

        return event
