import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.db.base import Base


class RawEvent(Base):
    """Raw governance event as received at the REST boundary (M1 skeleton).

    Stores the unmodified event body in JSONB; ``event_type`` is lifted out so
    the trace can be queried without unpacking JSON. Superseded by the full
    Event entity in M2.
    """

    __tablename__ = "raw_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AgentModel(Base):
    """Persistence model for a governed agent (M2)."""

    __tablename__ = "agents"

    agent_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(nullable=False)
    objective: Mapped[str] = mapped_column(nullable=False)
    vapi_assistant_id: Mapped[str] = mapped_column(unique=True, index=True, nullable=False)
    description: Mapped[str] = mapped_column(default="", nullable=False)
    status: Mapped[str] = mapped_column(nullable=False)


class SessionModel(Base):
    """Persistence model for a governance session (keyed by the Vapi call id)."""

    __tablename__ = "sessions"

    session_id: Mapped[str] = mapped_column(primary_key=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.agent_id"), nullable=False)
    status: Mapped[str] = mapped_column(nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EventModel(Base):
    """Persistence model for a canonical event within a session's trace."""

    __tablename__ = "events"

    event_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.session_id"), index=True, nullable=False
    )
    event_type: Mapped[str] = mapped_column(nullable=False)
    source: Mapped[str] = mapped_column(nullable=False)
    sequence_number: Mapped[int] = mapped_column(nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class EvidenceModel(Base):
    """Persistence model for an evidence built from a session's trace (M3)."""

    __tablename__ = "evidences"

    evidence_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.session_id"), index=True, nullable=False
    )
    evidence_type: Mapped[str] = mapped_column(nullable=False)
    criterion: Mapped[str] = mapped_column(nullable=False)
    conclusion: Mapped[str] = mapped_column(nullable=False)
    value: Mapped[float | None] = mapped_column(nullable=True)
    dimension: Mapped[str] = mapped_column(nullable=False)
    source_events: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
