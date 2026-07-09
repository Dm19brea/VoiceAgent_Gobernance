from src.domain.agent import Agent
from src.domain.evaluation_report import EvaluationReport
from src.domain.event import Event
from src.domain.evidence import Evidence
from src.domain.session import Session


class InMemoryGovernanceRepository:
    """In-memory double implementing the GovernanceRepository port for tests."""

    def __init__(self) -> None:
        self.agents: dict[str, Agent] = {}  # keyed by vapi_assistant_id
        self.sessions: dict[str, Session] = {}  # keyed by session_id
        self.evidences: dict[str, list[Evidence]] = {}  # keyed by session_id
        self.reports: dict[str, EvaluationReport] = {}  # keyed by session_id
        self.marker_events: list[Event] = []
        self.locked_session_ids: list[str] = []

    async def get_agent_by_assistant_id(self, assistant_id: str) -> Agent | None:
        return self.agents.get(assistant_id)

    async def add_agent(self, agent: Agent) -> None:
        self.agents[agent.vapi_assistant_id] = agent

    async def get_session(self, session_id: str) -> Session | None:
        return self.sessions.get(session_id)

    async def get_session_for_update(self, session_id: str) -> Session | None:
        self.locked_session_ids.append(session_id)
        return self.sessions.get(session_id)

    async def create_session(self, session: Session) -> bool:
        if session.session_id in self.sessions:
            return False
        self.sessions[session.session_id] = session
        return True

    async def save_session(self, session: Session) -> None:
        self.sessions[session.session_id] = session

    async def append_event(self, event: Event) -> bool:
        session = self.sessions.get(event.session_id)
        if session is None:
            return False
        if any(existing.event_id == event.event_id for existing in session.events):
            return False
        session.events.append(event)
        return True

    async def append_marker_event(self, event: Event) -> None:
        self.marker_events.append(event)

    async def add_evidences(self, evidences: list[Evidence]) -> None:
        for evidence in evidences:
            self.evidences.setdefault(evidence.session_id, []).append(evidence)

    async def get_evidences_by_session(self, session_id: str) -> list[Evidence]:
        return self.evidences.get(session_id, [])

    async def add_report(self, report: EvaluationReport) -> None:
        self.reports[report.session_id] = report  # one report per session (replace)

    async def get_report_by_session(self, session_id: str) -> EvaluationReport | None:
        return self.reports.get(session_id)
