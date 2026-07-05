from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.agent import Agent
from src.domain.enums import AgentStatus, Dimension, EventType, EvidenceType, SessionStatus, Source
from src.domain.event import Event
from src.domain.evidence import Evidence
from src.domain.session import Session
from src.infrastructure.db.models import AgentModel, EventModel, EvidenceModel, SessionModel


class SqlAlchemyGovernanceRepository:
    """SQLAlchemy implementation of the GovernanceRepository port."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_agent_by_assistant_id(self, assistant_id: str) -> Agent | None:
        row = await self._session.scalar(
            select(AgentModel).where(AgentModel.vapi_assistant_id == assistant_id)
        )
        return _to_agent(row) if row is not None else None

    async def add_agent(self, agent: Agent) -> None:
        self._session.add(_to_agent_model(agent))
        await self._session.flush()

    async def get_session(self, session_id: str) -> Session | None:
        row = await self._session.scalar(
            select(SessionModel).where(SessionModel.session_id == session_id)
        )
        if row is None:
            return None
        event_rows = (
            await self._session.scalars(
                select(EventModel)
                .where(EventModel.session_id == session_id)
                .order_by(EventModel.sequence_number)
            )
        ).all()
        return _to_session(row, list(event_rows))

    async def save_session(self, session: Session) -> None:
        await self._session.merge(_to_session_model(session))
        for event in session.events:
            stmt = (
                pg_insert(EventModel)
                .values(**_event_values(event))
                .on_conflict_do_nothing(index_elements=["event_id"])
            )
            await self._session.execute(stmt)

    async def add_evidences(self, evidences: list[Evidence]) -> None:
        for evidence in evidences:
            self._session.add(_to_evidence_model(evidence))
        await self._session.flush()

    async def get_evidences_by_session(self, session_id: str) -> list[Evidence]:
        rows = (
            await self._session.scalars(
                select(EvidenceModel).where(EvidenceModel.session_id == session_id)
            )
        ).all()
        return [_to_evidence(row) for row in rows]


def _to_agent(row: AgentModel) -> Agent:
    return Agent(
        name=row.name,
        objective=row.objective,
        vapi_assistant_id=row.vapi_assistant_id,
        description=row.description,
        status=AgentStatus(row.status),
        agent_id=row.agent_id,
    )


def _to_agent_model(agent: Agent) -> AgentModel:
    return AgentModel(
        agent_id=agent.agent_id,
        name=agent.name,
        objective=agent.objective,
        vapi_assistant_id=agent.vapi_assistant_id,
        description=agent.description,
        status=agent.status.value,
    )


def _to_session(row: SessionModel, event_rows: list[EventModel]) -> Session:
    return Session(
        session_id=row.session_id,
        agent_id=row.agent_id,
        started_at=row.started_at,
        status=SessionStatus(row.status),
        ended_at=row.ended_at,
        events=[_to_event(event) for event in event_rows],
    )


def _to_session_model(session: Session) -> SessionModel:
    return SessionModel(
        session_id=session.session_id,
        agent_id=session.agent_id,
        status=session.status.value,
        started_at=session.started_at,
        ended_at=session.ended_at,
    )


def _to_event(row: EventModel) -> Event:
    return Event(
        session_id=row.session_id,
        event_type=EventType(row.event_type),
        source=Source(row.source),
        sequence_number=row.sequence_number,
        timestamp=row.timestamp,
        payload=row.payload,
        event_id=row.event_id,
    )


def _event_values(event: Event) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "session_id": event.session_id,
        "event_type": event.event_type.value,
        "source": event.source.value,
        "sequence_number": event.sequence_number,
        "timestamp": event.timestamp,
        "payload": event.payload,
    }


def _to_evidence_model(evidence: Evidence) -> EvidenceModel:
    return EvidenceModel(
        evidence_id=evidence.evidence_id,
        session_id=evidence.session_id,
        evidence_type=evidence.evidence_type.value,
        criterion=evidence.criterion,
        conclusion=evidence.conclusion,
        value=evidence.value,
        dimension=evidence.dimension.value,
        source_events=[str(event_id) for event_id in evidence.source_events],
        generated_at=evidence.generated_at,
    )


def _to_evidence(row: EvidenceModel) -> Evidence:
    return Evidence(
        session_id=row.session_id,
        evidence_type=EvidenceType(row.evidence_type),
        criterion=row.criterion,
        conclusion=row.conclusion,
        dimension=Dimension(row.dimension),
        source_events=[UUID(event_id) for event_id in row.source_events],
        value=row.value,
        evidence_id=row.evidence_id,
        generated_at=row.generated_at,
    )
