"""PR1 — SqlAlchemyGovernanceRepository.upsert_agent against the real test DB (R3-R7)."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.agent import Agent
from src.domain.enums import AgentStatus
from src.infrastructure.db.models import AgentModel
from src.infrastructure.repositories.governance_repository import SqlAlchemyGovernanceRepository


async def test_upsert_creates_new_agent(db_session: AsyncSession) -> None:
    repo = SqlAlchemyGovernanceRepository(db_session)

    agent = await repo.upsert_agent(
        Agent(name="Citas", objective="Confirmar", vapi_assistant_id="va-1", description="d")
    )
    await db_session.commit()

    assert agent.status is AgentStatus.ACTIVE
    row_count = await db_session.scalar(select(func.count()).select_from(AgentModel))
    assert row_count == 1


async def test_upsert_on_conflict_preserves_agent_id_and_no_duplicate_row(
    db_session: AsyncSession,
) -> None:
    repo = SqlAlchemyGovernanceRepository(db_session)
    created = await repo.upsert_agent(
        Agent(
            name="Old",
            objective="Old obj",
            vapi_assistant_id="va-2",
            description="old",
            status=AgentStatus.UNREGISTERED,
        )
    )
    await db_session.commit()

    updated = await repo.upsert_agent(
        Agent(name="New", objective="New obj", vapi_assistant_id="va-2", description="new")
    )
    await db_session.commit()

    assert updated.agent_id == created.agent_id
    assert updated.status is AgentStatus.ACTIVE
    assert updated.name == "New"
    row_count = await db_session.scalar(
        select(func.count()).select_from(AgentModel).where(AgentModel.vapi_assistant_id == "va-2")
    )
    assert row_count == 1


async def test_upsert_omitted_description_preserves_prior_value(db_session: AsyncSession) -> None:
    repo = SqlAlchemyGovernanceRepository(db_session)
    await repo.upsert_agent(
        Agent(name="Citas", objective="Confirmar", vapi_assistant_id="va-3", description="kept")
    )
    await db_session.commit()

    updated = await repo.upsert_agent(
        Agent(
            name="Citas",
            objective="Confirmar",
            vapi_assistant_id="va-3",
            description=None,
        )
    )
    await db_session.commit()

    assert updated.description == "kept"


async def test_upsert_provided_description_overwrites_prior_value(db_session: AsyncSession) -> None:
    repo = SqlAlchemyGovernanceRepository(db_session)
    await repo.upsert_agent(
        Agent(name="Citas", objective="Confirmar", vapi_assistant_id="va-4", description="first")
    )
    await db_session.commit()

    updated = await repo.upsert_agent(
        Agent(
            name="Citas",
            objective="Confirmar",
            vapi_assistant_id="va-4",
            description="second",
        )
    )
    await db_session.commit()

    assert updated.description == "second"
