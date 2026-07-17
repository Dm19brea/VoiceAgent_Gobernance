from uuid import UUID

from src.application.ports.governance_repository import GovernanceRepository
from src.domain.agent import Agent


class ActivateAgent:
    """Turn on webhook credential activation for an agent (PR3).

    Returns ``None`` when the agent does not exist or is soft-deleted, so the
    caller (the REST route) can map that to a 404. Activating an already
    activated agent is idempotent — it returns the current state with no
    error, unlike soft-delete (S6).
    """

    def __init__(self, repository: GovernanceRepository) -> None:
        self._repo = repository

    async def execute(self, agent_id: UUID) -> Agent | None:
        return await self._repo.set_webhook_activated(agent_id, activated=True)


class DeactivateAgent:
    """Turn off webhook credential activation for an agent (PR3).

    Returns ``None`` when the agent does not exist or is soft-deleted, so the
    caller (the REST route) can map that to a 404. Deactivating an already
    deactivated agent is idempotent — it returns the current state with no
    error.
    """

    def __init__(self, repository: GovernanceRepository) -> None:
        self._repo = repository

    async def execute(self, agent_id: UUID) -> Agent | None:
        return await self._repo.set_webhook_activated(agent_id, activated=False)
