from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.agent import Agent
from src.domain.enums import AgentStatus, EventType, SessionStatus, Source
from src.domain.event import Event
from src.domain.session import Session
from src.infrastructure.db.models import AgentModel, EventModel, SessionModel


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
