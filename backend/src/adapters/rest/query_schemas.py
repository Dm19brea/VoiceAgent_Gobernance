"""Response schemas for the query API (doc 4.4 §4.4.3, Grupo 3)."""

from datetime import datetime
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
    status: str
    started_at: datetime
    ended_at: datetime | None
    result: str
    score_global: float | None
