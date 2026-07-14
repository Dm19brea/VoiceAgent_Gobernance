from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from src.domain.agent import Agent
from src.domain.enums import EvaluationResult, EventType, SessionStatus, Source
from src.domain.evaluation_report import EvaluationReport
from src.domain.event import Event
from src.domain.evidence import Evidence
from src.domain.session import Session


@dataclass(frozen=True, slots=True)
class SessionSummary:
    """Read projection of a session plus its evaluation outcome (M5.1, R6).

    ``result``/``score_global`` are ``None`` while the session is unevaluated (pending).
    """

    session_id: str
    agent_id: UUID
    status: SessionStatus
    started_at: datetime
    ended_at: datetime | None
    result: EvaluationResult | None
    score_global: float | None


class GovernanceQuery(Protocol):
    """Read boundary (CQRS-light), separate from the write repository (R1, R10).

    Returns domain entities and read DTOs shaped for the API; never leaks SQLAlchemy.
    """

    async def get_session(self, session_id: str) -> Session | None: ...

    async def get_events(
        self,
        session_id: str,
        *,
        event_type: EventType | None = None,
        source: Source | None = None,
    ) -> list[Event]: ...

    async def get_evidences(self, session_id: str) -> list[Evidence]: ...

    async def get_report(self, session_id: str) -> EvaluationReport | None: ...

    async def list_sessions(self, *, limit: int = 50, offset: int = 0) -> list[SessionSummary]: ...

    async def list_agent_sessions(
        self,
        agent_id: UUID,
        *,
        result: EvaluationResult | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SessionSummary]: ...

    async def list_agents(self) -> list[Agent]: ...
