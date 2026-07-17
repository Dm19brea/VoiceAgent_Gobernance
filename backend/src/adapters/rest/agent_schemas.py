"""Request/response schemas for agent registration (PR1, R1-R2, R6)."""

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, StringConstraints

from src.application.commands import RegisterAgentCommand

TrimmedStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class RegisterAgentIn(BaseModel):
    """``POST /agents`` request body. ``description`` omitted means "unchanged"."""

    vapi_assistant_id: TrimmedStr
    name: TrimmedStr
    objective: TrimmedStr
    description: str | None = None

    def to_command(self) -> RegisterAgentCommand:
        return RegisterAgentCommand(
            vapi_assistant_id=self.vapi_assistant_id,
            name=self.name,
            objective=self.objective,
            description=self.description,
        )


class AgentOut(BaseModel):
    """The full persisted agent (``POST /agents`` response, R6)."""

    agent_id: UUID
    name: str
    objective: str
    description: str | None
    vapi_assistant_id: str
    status: str
    webhook_activated: bool
