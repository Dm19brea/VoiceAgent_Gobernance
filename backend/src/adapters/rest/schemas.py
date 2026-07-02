from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class EventIn(BaseModel):
    """Input contract for a governance event received at the REST boundary.

    Minimal M1 shape: structural validation only. Mapping from provider-specific
    field names (e.g. Vapi) to canonical governance events is deferred to M2.
    """

    event_type: str = Field(min_length=1)
    agent_id: UUID
    timestamp: datetime
    source: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
