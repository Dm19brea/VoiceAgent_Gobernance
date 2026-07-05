from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.agent import Agent
from src.domain.enums import EventType, Source
from src.domain.session import Session
from src.infrastructure.celery.tasks import build_session_evidences_async
from src.infrastructure.repositories.governance_repository import SqlAlchemyGovernanceRepository

START = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
END = datetime(2026, 1, 1, 10, 0, 30, tzinfo=UTC)


async def test_task_builds_and_persists_evidences(db_session: AsyncSession) -> None:
    repo = SqlAlchemyGovernanceRepository(db_session)
    agent = Agent(name="Citas", objective="Confirmar", vapi_assistant_id="asst-t8")
    await repo.add_agent(agent)

    session = Session.open("call-t8", agent.agent_id, START)
    report = {"report": {"ended_reason": "ok"}}
    session.record(EventType.SESSION_STARTED, Source.PLATFORM, START, {})
    session.record(EventType.CONVERSATION_USER_INPUT, Source.USER, START, {})
    session.record(EventType.SESSION_ENDED, Source.PLATFORM, END, report)
    await repo.save_session(session)
    await db_session.commit()

    count = await build_session_evidences_async("call-t8")

    assert count > 0
    evidences = await repo.get_evidences_by_session("call-t8")
    assert len(evidences) > 0
    assert any(e.criterion == "ended_reason" for e in evidences)


async def test_task_on_unknown_session_returns_zero(db_session: AsyncSession) -> None:
    count = await build_session_evidences_async("does-not-exist")

    assert count == 0
