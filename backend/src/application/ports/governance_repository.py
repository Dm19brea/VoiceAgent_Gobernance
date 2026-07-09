from typing import Protocol

from src.domain.agent import Agent
from src.domain.evaluation_report import EvaluationReport
from src.domain.event import Event
from src.domain.evidence import Evidence
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

    async def get_session_for_update(self, session_id: str) -> Session | None: ...

    async def create_session(self, session: Session) -> bool: ...

    async def save_session(self, session: Session) -> None: ...

    async def append_event(self, event: Event) -> bool: ...

    async def append_marker_event(self, event: Event) -> None: ...

    async def add_evidences(self, evidences: list[Evidence]) -> None: ...

    async def get_evidences_by_session(self, session_id: str) -> list[Evidence]: ...

    async def add_report(self, report: EvaluationReport) -> None: ...

    async def get_report_by_session(self, session_id: str) -> EvaluationReport | None: ...
