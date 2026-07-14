"""PR1 — RegisterAgent use case over an in-memory repository (S1-S3, R9, description rule)."""

from src.application.commands import RegisterAgentCommand
from src.application.use_cases.register_agent import RegisterAgent
from src.domain.agent import Agent
from src.domain.enums import AgentStatus
from tests.fakes import InMemoryGovernanceRepository


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

    agent = await RegisterAgent(repo).execute(_cmd())

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

    agent = await RegisterAgent(repo).execute(
        _cmd(vapi_assistant_id="va-2", name="Citas", objective="Confirmar")
    )

    assert agent.agent_id == unregistered.agent_id
    assert agent.status is AgentStatus.ACTIVE
    assert agent.name == "Citas"
    assert agent.objective == "Confirmar"
    assert len(repo.agents) == 1


async def test_register_twice_is_idempotent_latest_wins() -> None:
    repo = InMemoryGovernanceRepository()

    await RegisterAgent(repo).execute(_cmd(vapi_assistant_id="va-3", name="Old"))
    agent = await RegisterAgent(repo).execute(_cmd(vapi_assistant_id="va-3", name="New"))

    assert len(repo.agents) == 1
    assert agent.name == "New"


async def test_register_with_description_provided_overwrites_prior() -> None:
    repo = InMemoryGovernanceRepository()
    await RegisterAgent(repo).execute(_cmd(vapi_assistant_id="va-4", description="first"))

    agent = await RegisterAgent(repo).execute(_cmd(vapi_assistant_id="va-4", description="second"))

    assert agent.description == "second"


async def test_register_with_description_omitted_preserves_prior() -> None:
    repo = InMemoryGovernanceRepository()
    await RegisterAgent(repo).execute(_cmd(vapi_assistant_id="va-5", description="kept"))

    agent = await RegisterAgent(repo).execute(
        RegisterAgentCommand(
            vapi_assistant_id="va-5", name="Citas", objective="Confirmar", description=None
        )
    )

    assert agent.description == "kept"
