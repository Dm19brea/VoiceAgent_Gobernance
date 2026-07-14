from src.application.commands import RegisterAgentCommand
from src.application.ports.governance_repository import GovernanceRepository
from src.domain.agent import Agent
from src.domain.enums import AgentStatus


class RegisterAgent:
    """Register a new agent or promote an existing one (e.g. auto-provisioned
    UNREGISTERED) to ACTIVE, keyed by ``vapi_assistant_id``.
    """

    def __init__(self, repository: GovernanceRepository) -> None:
        self._repo = repository

    async def execute(self, command: RegisterAgentCommand) -> Agent:
        agent = Agent(
            name=command.name,
            objective=command.objective,
            vapi_assistant_id=command.vapi_assistant_id,
            description=command.description,
            status=AgentStatus.ACTIVE,
        )
        return await self._repo.upsert_agent(agent)
