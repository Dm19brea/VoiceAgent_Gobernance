from src.domain.agent import Agent
from src.domain.evidence import Evidence
from src.domain.session import Session


class InMemoryGovernanceRepository:
    """In-memory double implementing the GovernanceRepository port for tests."""

    def __init__(self) -> None:
        self.agents: dict[str, Agent] = {}  # keyed by vapi_assistant_id
        self.sessions: dict[str, Session] = {}  # keyed by session_id
        self.evidences: dict[str, list[Evidence]] = {}  # keyed by session_id

    async def get_agent_by_assistant_id(self, assistant_id: str) -> Agent | None:
        return self.agents.get(assistant_id)

    async def add_agent(self, agent: Agent) -> None:
        self.agents[agent.vapi_assistant_id] = agent

    async def get_session(self, session_id: str) -> Session | None:
        return self.sessions.get(session_id)

    async def save_session(self, session: Session) -> None:
        self.sessions[session.session_id] = session

    async def add_evidences(self, evidences: list[Evidence]) -> None:
        for evidence in evidences:
            self.evidences.setdefault(evidence.session_id, []).append(evidence)

    async def get_evidences_by_session(self, session_id: str) -> list[Evidence]:
        return self.evidences.get(session_id, [])
