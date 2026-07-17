"""PR1 (agent-webhook-activation) — repository/mapper support for
``webhook_activated`` (Requirement: Per-Agent Webhook Activation Flag)."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.agent import Agent
from src.infrastructure.repositories.governance_repository import (
    SqlAlchemyGovernanceRepository,
    _to_agent,
    _to_agent_model,
)

DELETED_AT = datetime(2026, 2, 1, 12, 0, 0, tzinfo=UTC)


def test_to_agent_model_round_trips_webhook_activated() -> None:
    agent = Agent(
        name="Citas",
        objective="Confirmar",
        vapi_assistant_id="asst-map-1",
        webhook_activated=True,
    )

    model = _to_agent_model(agent)

    assert model.webhook_activated is True

    rebuilt = _to_agent(model)

    assert rebuilt.webhook_activated is True


async def test_upsert_agent_new_agent_defaults_webhook_activated_false(
    db_session: AsyncSession,
) -> None:
    repo = SqlAlchemyGovernanceRepository(db_session)

    agent = await repo.upsert_agent(
        Agent(name="Citas", objective="Confirmar", vapi_assistant_id="asst-map-2")
    )
    await db_session.commit()

    assert agent.webhook_activated is False


async def test_upsert_agent_preserves_webhook_activated_on_reregister(
    db_session: AsyncSession,
) -> None:
    """Re-registering a previously activated agent MUST preserve its
    activation state: ``webhook_activated`` is excluded from ``upsert_agent``'s
    ``on_conflict`` ``set_``."""
    repo = SqlAlchemyGovernanceRepository(db_session)
    created = await repo.upsert_agent(
        Agent(name="Citas", objective="Confirmar", vapi_assistant_id="asst-map-3")
    )
    await db_session.commit()

    activated = await repo.set_webhook_activated(created.agent_id, activated=True)
    await db_session.commit()
    assert activated is not None
    assert activated.webhook_activated is True

    reregistered = await repo.upsert_agent(
        Agent(name="New Name", objective="New obj", vapi_assistant_id="asst-map-3")
    )
    await db_session.commit()

    assert reregistered.agent_id == created.agent_id
    assert reregistered.webhook_activated is True


async def test_set_webhook_activated_true_returns_updated_agent(
    db_session: AsyncSession,
) -> None:
    repo = SqlAlchemyGovernanceRepository(db_session)
    agent = await repo.upsert_agent(
        Agent(name="Citas", objective="Confirmar", vapi_assistant_id="asst-set-1")
    )
    await db_session.commit()

    updated = await repo.set_webhook_activated(agent.agent_id, activated=True)
    await db_session.commit()

    assert updated is not None
    assert updated.webhook_activated is True
    assert updated.agent_id == agent.agent_id


async def test_set_webhook_activated_false_returns_updated_agent(
    db_session: AsyncSession,
) -> None:
    repo = SqlAlchemyGovernanceRepository(db_session)
    agent = await repo.upsert_agent(
        Agent(name="Citas", objective="Confirmar", vapi_assistant_id="asst-set-2")
    )
    await db_session.commit()
    await repo.set_webhook_activated(agent.agent_id, activated=True)
    await db_session.commit()

    updated = await repo.set_webhook_activated(agent.agent_id, activated=False)
    await db_session.commit()

    assert updated is not None
    assert updated.webhook_activated is False


async def test_set_webhook_activated_unknown_agent_returns_none(
    db_session: AsyncSession,
) -> None:
    repo = SqlAlchemyGovernanceRepository(db_session)

    result = await repo.set_webhook_activated(uuid4(), activated=True)

    assert result is None


async def test_set_webhook_activated_soft_deleted_agent_returns_none(
    db_session: AsyncSession,
) -> None:
    repo = SqlAlchemyGovernanceRepository(db_session)
    agent = await repo.upsert_agent(
        Agent(name="Citas", objective="Confirmar", vapi_assistant_id="asst-set-3")
    )
    await db_session.commit()
    await repo.soft_delete_agent(agent.agent_id, deleted_at=DELETED_AT)
    await db_session.commit()

    result = await repo.set_webhook_activated(agent.agent_id, activated=True)

    assert result is None
