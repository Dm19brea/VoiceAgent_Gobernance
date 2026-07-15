from src.application.commands import RegisterAgentCommand
from src.application.errors import AssistantNotFoundError
from src.application.ports.assistant_directory import AssistantDirectory
from src.application.ports.governance_repository import GovernanceRepository
from src.domain.agent import Agent
from src.domain.enums import AgentStatus


class RegisterAgent:
    """Register a new agent or promote an existing one (e.g. auto-provisioned
    UNREGISTERED) to ACTIVE, keyed by ``vapi_assistant_id``.

    Verifies the assistant exists in Vapi (fail-closed) before persisting:
    ``AssistantNotFoundError`` and ``AssistantDirectoryUnavailable`` propagate
    to the caller and no upsert occurs.
    """

    def __init__(self, repository: GovernanceRepository, directory: AssistantDirectory) -> None:
        self._repo = repository
        self._directory = directory

    async def execute(self, command: RegisterAgentCommand) -> Agent:
        if not await self._directory.exists(command.vapi_assistant_id):
            raise AssistantNotFoundError(command.vapi_assistant_id)

        agent = Agent(
            name=command.name,
            objective=command.objective,
            vapi_assistant_id=command.vapi_assistant_id,
            description=command.description,
            status=AgentStatus.ACTIVE,
        )
        return await self._repo.upsert_agent(agent)
