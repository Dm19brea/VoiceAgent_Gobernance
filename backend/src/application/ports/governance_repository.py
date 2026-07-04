from typing import Protocol

from src.domain.agent import Agent
from src.domain.session import Session


class GovernanceRepository(Protocol):
    """Persistence boundary for the governance aggregate.

    Aggregate-oriented: a ``Session`` is loaded and saved as a whole (with its
    events), keeping sequence assignment inside the domain. The application
    depends on this interface, never on SQLAlchemy.
    """

    async def get_agent_by_assistant_id(self, assistant_id: str) -> Agent | None: ...

    async def add_agent(self, agent: Agent) -> None: ...

    async def get_session(self, session_id: str) -> Session | None: ...

    async def save_session(self, session: Session) -> None: ...
