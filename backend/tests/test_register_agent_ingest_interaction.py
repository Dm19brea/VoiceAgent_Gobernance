"""PR1 — S4: IngestEvent must not overwrite a pre-registered ACTIVE agent."""

from datetime import UTC, datetime

from src.application.commands import IngestEventCommand, RegisterAgentCommand
from src.application.use_cases.ingest_event import IngestEvent
from src.application.use_cases.register_agent import RegisterAgent
from src.domain.enums import AgentStatus, EventType, Source
from tests.fakes import InMemoryGovernanceRepository


async def test_ingest_event_uses_preregistered_active_agent_unchanged() -> None:
    repo = InMemoryGovernanceRepository()
    registered = await RegisterAgent(repo).execute(
        RegisterAgentCommand(vapi_assistant_id="va-4", name="Citas", objective="Confirmar")
    )

    await IngestEvent(repo).execute(
        IngestEventCommand(
            call_id="call-1",
            assistant_id="va-4",
            event_type=EventType.SESSION_STARTED,
            source=Source.PLATFORM,
            timestamp=datetime.now(UTC),
            payload={},
        )
    )

    agent = await repo.get_agent_by_assistant_id("va-4")
    assert agent is not None
    assert agent.agent_id == registered.agent_id
    assert agent.status is AgentStatus.ACTIVE
    assert agent.name == "Citas"
    assert agent.objective == "Confirmar"
