"""PR3 — ActivateAgent/DeactivateAgent use cases over an in-memory repository."""

from uuid import uuid4

from src.application.use_cases.activate_agent import ActivateAgent, DeactivateAgent
from src.domain.agent import Agent
from tests.fakes import InMemoryGovernanceRepository


async def test_activate_agent_sets_flag_true() -> None:
    repo = InMemoryGovernanceRepository()
    agent = Agent(
        name="Citas", objective="Confirmar", vapi_assistant_id="va-1", webhook_activated=False
    )
    await repo.add_agent(agent)

    result = await ActivateAgent(repo).execute(agent.agent_id)

    assert result is not None
    assert result.webhook_activated is True


async def test_deactivate_agent_sets_flag_false() -> None:
    repo = InMemoryGovernanceRepository()
    agent = Agent(
        name="Citas", objective="Confirmar", vapi_assistant_id="va-2", webhook_activated=True
    )
    await repo.add_agent(agent)

    result = await DeactivateAgent(repo).execute(agent.agent_id)

    assert result is not None
    assert result.webhook_activated is False


async def test_activate_unknown_agent_returns_none() -> None:
    repo = InMemoryGovernanceRepository()

    result = await ActivateAgent(repo).execute(uuid4())

    assert result is None


async def test_deactivate_unknown_agent_returns_none() -> None:
    repo = InMemoryGovernanceRepository()

    result = await DeactivateAgent(repo).execute(uuid4())

    assert result is None
