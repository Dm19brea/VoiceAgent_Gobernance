"""PR2 — soft delete repository/query behavior (R2, S5, S7, S8)."""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.agent import Agent
from src.domain.enums import EventType, Source
from src.domain.session import Session
from src.infrastructure.repositories.governance_query import SqlAlchemyGovernanceQuery
from src.infrastructure.repositories.governance_repository import SqlAlchemyGovernanceRepository

DELETED_AT = datetime(2026, 2, 1, 12, 0, 0, tzinfo=UTC)
START = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)


async def test_soft_delete_sets_deleted_at_and_excludes_from_lookup(
    db_session: AsyncSession,
) -> None:
    """S5 — deleting sets deleted_at; get_agent_by_assistant_id no longer finds it."""
    repo = SqlAlchemyGovernanceRepository(db_session)
    agent = await repo.upsert_agent(
        Agent(name="Citas", objective="Confirmar", vapi_assistant_id="asst-del-1")
    )
    await db_session.commit()

    deleted = await repo.soft_delete_agent(agent.agent_id, deleted_at=DELETED_AT)
    await db_session.commit()

    assert deleted is True
    assert await repo.get_agent_by_assistant_id("asst-del-1") is None


async def test_soft_delete_unknown_agent_returns_false(db_session: AsyncSession) -> None:
    """S6 (repo level) — deleting a non-existent agent_id is a no-op, returns False."""
    from uuid import uuid4

    repo = SqlAlchemyGovernanceRepository(db_session)

    deleted = await repo.soft_delete_agent(uuid4(), deleted_at=DELETED_AT)

    assert deleted is False


async def test_soft_delete_already_deleted_agent_returns_false(db_session: AsyncSession) -> None:
    """S6 (repo level) — deleting an already-deleted agent is not idempotent-success."""
    repo = SqlAlchemyGovernanceRepository(db_session)
    agent = await repo.upsert_agent(
        Agent(name="Citas", objective="Confirmar", vapi_assistant_id="asst-del-2")
    )
    await db_session.commit()
    await repo.soft_delete_agent(agent.agent_id, deleted_at=DELETED_AT)
    await db_session.commit()

    deleted_again = await repo.soft_delete_agent(agent.agent_id, deleted_at=DELETED_AT)

    assert deleted_again is False


async def test_soft_delete_preserves_session_history(db_session: AsyncSession) -> None:
    """S7 — sessions/events/reports for a soft-deleted agent remain intact."""
    repo = SqlAlchemyGovernanceRepository(db_session)
    agent = await repo.upsert_agent(
        Agent(name="Citas", objective="Confirmar", vapi_assistant_id="asst-del-3")
    )
    session = Session.open("call-del-3", agent.agent_id, START)
    session.record(EventType.SESSION_STARTED, Source.PLATFORM, START, {})
    await repo.save_session(session)
    await db_session.commit()

    await repo.soft_delete_agent(agent.agent_id, deleted_at=DELETED_AT)
    await db_session.commit()

    reloaded = await repo.get_session("call-del-3")
    assert reloaded is not None
    assert len(reloaded.events) == 1


async def test_list_agents_excludes_soft_deleted_deterministic_order(
    db_session: AsyncSession,
) -> None:
    """S8 — GET /agents (list_agents) excludes soft-deleted agents, stable order."""
    repo = SqlAlchemyGovernanceRepository(db_session)
    active_a = await repo.upsert_agent(
        Agent(name="A Agent", objective="obj", vapi_assistant_id="asst-list-a")
    )
    to_delete = await repo.upsert_agent(
        Agent(name="B Agent", objective="obj", vapi_assistant_id="asst-list-b")
    )
    active_c = await repo.upsert_agent(
        Agent(name="C Agent", objective="obj", vapi_assistant_id="asst-list-c")
    )
    await db_session.commit()
    await repo.soft_delete_agent(to_delete.agent_id, deleted_at=DELETED_AT)
    await db_session.commit()

    query = SqlAlchemyGovernanceQuery(db_session)
    first = await query.list_agents()
    second = await query.list_agents()

    assert [a.vapi_assistant_id for a in first] == ["asst-list-a", "asst-list-c"]
    assert [a.agent_id for a in first] == [active_a.agent_id, active_c.agent_id]
    assert first == second
