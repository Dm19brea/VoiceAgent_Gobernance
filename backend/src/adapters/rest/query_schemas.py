"""Response schemas for the query API (doc 4.4 §4.4.3, Grupo 3)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class SessionOut(BaseModel):
    """Session state and turn counters (GET /sessions/{id}, R2)."""

    session_id: str
    agent_id: UUID
    status: str
    started_at: datetime
    ended_at: datetime | None
    total_turns: int
    agent_turns: int
    user_turns: int


class SessionSummaryOut(BaseModel):
    """One row of an agent's session listing (GET /agents/{id}/sessions, R6).

    ``result`` is ``"pending"`` while the session has no evaluation report.
    """

    session_id: str
    agent_name: str
    status: str
    started_at: datetime
    ended_at: datetime | None
    result: str
    score_global: float | None


class ScoresOut(BaseModel):
    """Per-dimension scores; ``None`` for a dimension with no metrics (doc 4.4 report)."""

    conversational: float | None
    operational: float | None
    technical: float | None
    risk: float | None


class BlockingFlagOut(BaseModel):
    code: str
    reason: str


class ReportOut(BaseModel):
    """Evaluation report shaped per doc 4.4 §4.4.3 (GET /sessions/{id}/report, R5)."""

    report_id: UUID
    session_id: str
    score_global: float
    scores: ScoresOut
    result: str
    blocking_flags: list[BlockingFlagOut]
    generated_at: datetime


class EvidenceOut(BaseModel):
    """One evidence built from a session's trace (GET /sessions/{id}/evidences, R4)."""

    evidence_id: UUID
    session_id: str
    evidence_type: str
    criterion: str
    conclusion: str
    dimension: str
    value: float | None
    generated_at: datetime


class EventOut(BaseModel):
    """One canonical event of a session's trace (GET /sessions/{id}/events, R3)."""

    event_id: UUID
    session_id: str
    event_type: str
    source: str
    sequence_number: int
    timestamp: datetime
    payload: dict[str, Any]
