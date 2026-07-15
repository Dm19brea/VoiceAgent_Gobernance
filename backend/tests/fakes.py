from dataclasses import replace
from datetime import datetime
from uuid import UUID

from src.application.ports.assistant_directory import AssistantDirectoryUnavailable
from src.application.ports.conversation_judge import JudgeVerdict
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
        agent = self.agents.get(assistant_id)
        if agent is None or agent.deleted_at is not None:
            return None
        return agent

    async def add_agent(self, agent: Agent) -> None:
        self.agents[agent.vapi_assistant_id] = agent

    async def upsert_agent(self, agent: Agent) -> Agent:
        existing = self.agents.get(agent.vapi_assistant_id)
        if existing is not None:
            description = (
                agent.description if agent.description is not None else existing.description
            )
            resolved = replace(
                agent, agent_id=existing.agent_id, description=description, deleted_at=None
            )
        else:
            resolved = replace(agent, description=agent.description or "", deleted_at=None)
        self.agents[agent.vapi_assistant_id] = resolved
        return resolved

    async def soft_delete_agent(self, agent_id: UUID, *, deleted_at: datetime) -> bool:
        for assistant_id, agent in self.agents.items():
            if agent.agent_id == agent_id:
                if agent.deleted_at is not None:
                    return False
                self.agents[assistant_id] = replace(agent, deleted_at=deleted_at)
                return True
        return False

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


class FakeAssistantDirectory:
    """Deterministic double implementing the AssistantDirectory port for tests.

    ``exists=True`` (default) simulates a real Vapi assistant. ``exists=False``
    simulates a not-found assistant (returns ``False``; the use case is
    responsible for turning that into ``AssistantNotFoundError``).
    ``unavailable=True`` simulates a Vapi outage (raises
    ``AssistantDirectoryUnavailable``), taking precedence over ``exists``.
    """

    def __init__(self, exists: bool = True, unavailable: bool = False) -> None:
        self.exists_result = exists
        self.unavailable = unavailable
        self.calls: list[str] = []

    async def exists(self, assistant_id: str) -> bool:
        self.calls.append(assistant_id)
        if self.unavailable:
            raise AssistantDirectoryUnavailable(f"Vapi unavailable for {assistant_id}")
        return self.exists_result


class FakeConversationJudge:
    """Deterministic double implementing the ConversationJudge port for tests."""

    def __init__(self, verdict: JudgeVerdict | None) -> None:
        self.verdict = verdict
        self.calls: list[str] = []

    async def evaluate(self, transcript: str) -> JudgeVerdict | None:
        self.calls.append(transcript)
        return self.verdict
