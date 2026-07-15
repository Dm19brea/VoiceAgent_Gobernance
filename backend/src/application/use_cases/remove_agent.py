from src.application.commands import RemoveAgentCommand
from src.application.ports.governance_repository import GovernanceRepository


class RemoveAgent:
    """Soft-delete an agent (R2).

    Returns ``False`` when the agent does not exist or is already
    soft-deleted, so the caller (the REST route) can map that to a 404 —
    repeated delete is not idempotent-success (S6).
    """

    def __init__(self, repository: GovernanceRepository) -> None:
        self._repo = repository

    async def execute(self, command: RemoveAgentCommand) -> bool:
        return await self._repo.soft_delete_agent(command.agent_id, deleted_at=command.deleted_at)
