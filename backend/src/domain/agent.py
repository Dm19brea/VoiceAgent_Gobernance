from dataclasses import dataclass, field
from uuid import UUID, uuid4

from src.domain.enums import AgentStatus


@dataclass
class Agent:
    """A conversational voice agent governed by the platform."""

    name: str
    objective: str
    vapi_assistant_id: str
    description: str | None = ""
    """``None`` is a repository-level sentinel meaning "not provided": on
    ``upsert_agent`` it leaves a pre-existing description untouched instead of
    overwriting it. Never persisted as ``None``; a fresh insert stores ``""``.
    """
    status: AgentStatus = AgentStatus.ACTIVE
    agent_id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Agent name must not be empty")
        if not self.objective:
            raise ValueError("Agent objective must not be empty")
