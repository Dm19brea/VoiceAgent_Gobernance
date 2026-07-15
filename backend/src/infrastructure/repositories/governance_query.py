"""SQLAlchemy read adapter for the GovernanceQuery port (CQRS-light, M5.1).

Reuses the write repository's entity mapping for the single-aggregate reads and adds
read-optimised queries (filtered events, agent-session listing joined with reports).
"""

from typing import Any
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.ports.query import SessionSummary
from src.domain.agent import Agent
from src.domain.enums import EvaluationResult, EventType, SessionStatus, Source
from src.domain.evaluation_report import EvaluationReport
from src.domain.event import Event
from src.domain.evidence import Evidence
from src.domain.session import Session
from src.infrastructure.db.models import AgentModel, EvaluationReportModel, SessionModel
from src.infrastructure.repositories.governance_repository import (
    SqlAlchemyGovernanceRepository,
    _to_agent,
)


class SqlAlchemyGovernanceQuery:
    """Read side backed by the same session as the write repository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = SqlAlchemyGovernanceRepository(session)

    async def get_session(self, session_id: str) -> Session | None:
        return await self._repo.get_session(session_id)

    async def get_events(
        self,
        session_id: str,
        *,
        event_type: EventType | None = None,
        source: Source | None = None,
    ) -> list[Event]:
        session = await self._repo.get_session(session_id)
        if session is None:
            return []
        events = session.events  # already ordered by sequence_number
        if event_type is not None:
            events = [event for event in events if event.event_type is event_type]
        if source is not None:
            events = [event for event in events if event.source is source]
        return events

    async def get_evidences(self, session_id: str) -> list[Evidence]:
        return await self._repo.get_evidences_by_session(session_id)

    async def get_report(self, session_id: str) -> EvaluationReport | None:
        return await self._repo.get_report_by_session(session_id)

    async def list_agent_sessions(
        self,
        agent_id: UUID,
        *,
        result: EvaluationResult | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SessionSummary]:
        stmt = (
            _summary_select()
            .where(SessionModel.agent_id == agent_id)
            .order_by(SessionModel.started_at.desc())
        )
        if result is not None:
            stmt = stmt.where(EvaluationReportModel.result == result.value)
        stmt = stmt.limit(limit).offset(offset)

        rows = (await self._session.execute(stmt)).all()
        return [
            _to_summary(session_row, report_row, agent_name)
            for session_row, report_row, agent_name in rows
        ]

    async def list_sessions(self, *, limit: int = 50, offset: int = 0) -> list[SessionSummary]:
        stmt = (
            _summary_select().order_by(SessionModel.started_at.desc()).limit(limit).offset(offset)
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            _to_summary(session_row, report_row, agent_name)
            for session_row, report_row, agent_name in rows
        ]

    async def list_agents(self) -> list[Agent]:
        rows = (
            await self._session.scalars(
                select(AgentModel)
                .where(AgentModel.deleted_at.is_(None))
                .order_by(AgentModel.name, AgentModel.agent_id)
            )
        ).all()
        return [_to_agent(row) for row in rows]


def _summary_select() -> Select[Any]:
    """Shared select for session summaries (R1/R3, ADR-1/ADR-2).

    INNER JOIN to ``AgentModel`` resolves ``agent_name`` without a ``deleted_at``
    predicate, so a soft-deleted agent's sessions keep their name (R2). The
    optional evaluation report stays an OUTER JOIN since a session may be
    unevaluated (pending). Both ``list_sessions`` and ``list_agent_sessions``
    build on this so their emitted shape is byte-identical (R3/S4).
    """
    return (
        select(SessionModel, EvaluationReportModel, AgentModel.name)
        .join(AgentModel, SessionModel.agent_id == AgentModel.agent_id)
        .outerjoin(
            EvaluationReportModel,
            EvaluationReportModel.session_id == SessionModel.session_id,
        )
    )


def _to_summary(
    session_row: SessionModel, report_row: EvaluationReportModel | None, agent_name: str
) -> SessionSummary:
    return SessionSummary(
        session_id=session_row.session_id,
        agent_id=session_row.agent_id,
        agent_name=agent_name,
        status=SessionStatus(session_row.status),
        started_at=session_row.started_at,
        ended_at=session_row.ended_at,
        result=EvaluationResult(report_row.result) if report_row is not None else None,
        score_global=report_row.score_global if report_row is not None else None,
    )
