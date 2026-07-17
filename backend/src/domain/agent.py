from dataclasses import dataclass, field
from datetime import datetime
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
    deleted_at: datetime | None = None
    """``None`` while active; set by ``soft_delete_agent`` (R2). A soft-deleted
    agent is excluded from lookups and listings but its history is untouched.
    """
    webhook_activated: bool = False
    """Authorization flag gating whether the Vapi webhook accepts events for
    this agent. Defaults to ``False`` for newly registered and pre-existing
    agents; toggled via ``set_webhook_activated`` (activate/deactivate).
    """

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Agent name must not be empty")
        if not self.objective:
            raise ValueError("Agent objective must not be empty")
