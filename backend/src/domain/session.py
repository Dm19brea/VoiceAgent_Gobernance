from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from src.domain.enums import EventType, SessionStatus, Source
from src.domain.event import Event
from src.domain.exceptions import DomainError, SessionClosedError

_MARKER_EVENTS = frozenset({EventType.SESSION_EVALUATION_TRIGGERED})
_SYSTEM_OBSERVATION_EVENTS = frozenset(
    {
        EventType.SYSTEM_LATENCY_MEASURED,
        EventType.SYSTEM_ERROR,
        EventType.SYSTEM_FLAG_RAISED,
    }
)
_CONVERSATION_CONTENT_EVENTS = frozenset(
    {
        EventType.CONVERSATION_AGENT_RESPONSE,
        EventType.CONVERSATION_USER_INPUT,
    }
)


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

    def append_marker(
        self,
        event_type: EventType,
        source: Source,
        timestamp: datetime,
        payload: dict[str, Any],
    ) -> Event:
        """Append a post-terminal marker event, without touching status/ended_at.

        Unlike ``record``, this is only valid once the session is no longer
        active (the session must already be ENDED or FAILED), and only for
        the marker event set (e.g. ``session.evaluation_triggered``).
        """
        if self.status is SessionStatus.ACTIVE:
            raise SessionClosedError(f"Session {self.session_id} is still active")
        if event_type not in _MARKER_EVENTS:
            raise DomainError(f"{event_type} is not a valid marker event")

        event = Event(
            session_id=self.session_id,
            event_type=event_type,
            source=source,
            sequence_number=len(self.events) + 1,
            timestamp=timestamp,
            payload=payload,
        )
        self.events.append(event)

        return event

    def append_system_observation(
        self,
        event_type: EventType,
        source: Source,
        timestamp: datetime,
        payload: dict[str, Any],
        event_id: UUID | None = None,
    ) -> Event:
        """Append an allowed system observation without lifecycle mutation.

        Threat flags are valid while a call is active because Vapi delivers
        transcripts during the conversation. Latency and error observations
        remain post-terminal to preserve their completed-operation semantics.
        """
        if self.status is SessionStatus.ACTIVE and event_type is not EventType.SYSTEM_FLAG_RAISED:
            raise SessionClosedError(f"Session {self.session_id} is still active")
        if event_type not in _SYSTEM_OBSERVATION_EVENTS:
            raise DomainError(f"{event_type} is not a valid system observation")

        event = Event(
            session_id=self.session_id,
            event_type=event_type,
            source=source,
            sequence_number=len(self.events) + 1,
            timestamp=timestamp,
            payload=payload,
            **({"event_id": event_id} if event_id is not None else {}),
        )
        self.events.append(event)
        return event

    def append_conversation_content(
        self,
        event_type: EventType,
        source: Source,
        timestamp: datetime,
        payload: dict[str, Any],
        event_id: UUID | None = None,
    ) -> Event:
        """Append a post-terminal conversation content event (agent/user turn).

        Derived from the end-of-call-report after the session has closed, so
        this mirrors ``append_system_observation``: valid only once the
        session is no longer ACTIVE, and never mutates ``status``/``ended_at``.
        """
        if self.status is SessionStatus.ACTIVE:
            raise SessionClosedError(f"Session {self.session_id} is still active")
        if event_type not in _CONVERSATION_CONTENT_EVENTS:
            raise DomainError(f"{event_type} is not a valid conversation content event")

        event = Event(
            session_id=self.session_id,
            event_type=event_type,
            source=source,
            sequence_number=len(self.events) + 1,
            timestamp=timestamp,
            payload=payload,
            **({"event_id": event_id} if event_id is not None else {}),
        )
        self.events.append(event)
        return event
