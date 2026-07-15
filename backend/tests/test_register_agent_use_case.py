"""PR1 — RegisterAgent use case over an in-memory repository (S1-S4, R9, description rule)."""

import pytest

from src.application.commands import RegisterAgentCommand
from src.application.errors import AssistantNotFoundError
from src.application.ports.assistant_directory import AssistantDirectoryUnavailable
from src.application.use_cases.register_agent import RegisterAgent
from src.domain.agent import Agent
from src.domain.enums import AgentStatus
from tests.fakes import FakeAssistantDirectory, InMemoryGovernanceRepository


def _cmd(
    vapi_assistant_id: str = "va-1",
    name: str = "Citas",
    objective: str = "Confirmar",
    description: str | None = None,
) -> RegisterAgentCommand:
    return RegisterAgentCommand(
        vapi_assistant_id=vapi_assistant_id,
        name=name,
        objective=objective,
        description=description if description is not None else "",
    )


async def test_register_creates_new_active_agent() -> None:
    repo = InMemoryGovernanceRepository()

    agent = await RegisterAgent(repo, FakeAssistantDirectory()).execute(_cmd())

    assert agent.status is AgentStatus.ACTIVE
    assert agent.vapi_assistant_id == "va-1"
    assert agent.name == "Citas"
    assert agent.objective == "Confirmar"
    stored = await repo.get_agent_by_assistant_id("va-1")
    assert stored is not None
    assert stored.agent_id == agent.agent_id


async def test_register_promotes_unregistered_agent_preserving_agent_id() -> None:
    repo = InMemoryGovernanceRepository()
    unregistered = Agent(
        name="Unregistered va-2",
        objective="(unregistered)",
        vapi_assistant_id="va-2",
        status=AgentStatus.UNREGISTERED,
    )
    await repo.add_agent(unregistered)

    agent = await RegisterAgent(repo, FakeAssistantDirectory()).execute(
        _cmd(vapi_assistant_id="va-2", name="Citas", objective="Confirmar")
    )

    assert agent.agent_id == unregistered.agent_id
    assert agent.status is AgentStatus.ACTIVE
    assert agent.name == "Citas"
    assert agent.objective == "Confirmar"
    assert len(repo.agents) == 1


async def test_register_twice_is_idempotent_latest_wins() -> None:
    repo = InMemoryGovernanceRepository()

    await RegisterAgent(repo, FakeAssistantDirectory()).execute(
        _cmd(vapi_assistant_id="va-3", name="Old")
    )
    agent = await RegisterAgent(repo, FakeAssistantDirectory()).execute(
        _cmd(vapi_assistant_id="va-3", name="New")
    )

    assert len(repo.agents) == 1
    assert agent.name == "New"


async def test_register_with_description_provided_overwrites_prior() -> None:
    repo = InMemoryGovernanceRepository()
    await RegisterAgent(repo, FakeAssistantDirectory()).execute(
        _cmd(vapi_assistant_id="va-4", description="first")
    )

    agent = await RegisterAgent(repo, FakeAssistantDirectory()).execute(
        _cmd(vapi_assistant_id="va-4", description="second")
    )

    assert agent.description == "second"


async def test_register_with_description_omitted_preserves_prior() -> None:
    repo = InMemoryGovernanceRepository()
    await RegisterAgent(repo, FakeAssistantDirectory()).execute(
        _cmd(vapi_assistant_id="va-5", description="kept")
    )

    agent = await RegisterAgent(repo, FakeAssistantDirectory()).execute(
        RegisterAgentCommand(
            vapi_assistant_id="va-5", name="Citas", objective="Confirmar", description=None
        )
    )

    assert agent.description == "kept"


async def test_register_rejects_when_assistant_not_found_in_vapi() -> None:
    repo = InMemoryGovernanceRepository()
    directory = FakeAssistantDirectory(exists=False)

    with pytest.raises(AssistantNotFoundError):
        await RegisterAgent(repo, directory).execute(_cmd(vapi_assistant_id="va-missing"))

    assert await repo.get_agent_by_assistant_id("va-missing") is None


async def test_register_rejects_when_vapi_unavailable() -> None:
    repo = InMemoryGovernanceRepository()
    directory = FakeAssistantDirectory(unavailable=True)

    with pytest.raises(AssistantDirectoryUnavailable):
        await RegisterAgent(repo, directory).execute(_cmd(vapi_assistant_id="va-down"))

    assert await repo.get_agent_by_assistant_id("va-down") is None


async def test_register_calls_directory_with_exact_submitted_assistant_id() -> None:
    repo = InMemoryGovernanceRepository()
    directory = FakeAssistantDirectory(exists=True)

    await RegisterAgent(repo, directory).execute(_cmd(vapi_assistant_id="va-exact"))

    assert directory.calls == ["va-exact"]
