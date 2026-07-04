from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.agent import Agent
from src.domain.enums import EventType, Source
from src.domain.session import Session
from src.infrastructure.repositories.governance_repository import SqlAlchemyGovernanceRepository


async def test_repository_persists_and_reloads_session(db_session: AsyncSession) -> None:
    repo = SqlAlchemyGovernanceRepository(db_session)

    agent = Agent(name="Citas", objective="Confirmar", vapi_assistant_id="asst-x")
    await repo.add_agent(agent)

    session = Session.open("call-x", agent.agent_id, datetime.now(UTC))
    session.record(EventType.SESSION_STARTED, Source.PLATFORM, datetime.now(UTC), {})
    await repo.save_session(session)
    await db_session.commit()

    reloaded = await repo.get_session("call-x")
    assert reloaded is not None
    assert len(reloaded.events) == 1
    assert reloaded.events[0].event_type is EventType.SESSION_STARTED

    resolved = await repo.get_agent_by_assistant_id("asst-x")
    assert resolved is not None
    assert resolved.agent_id == agent.agent_id
