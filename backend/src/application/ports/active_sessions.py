from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ActiveSessionSnapshot:
    """Ephemeral view of a session in progress, for live supervision (M5.4)."""

    session_id: str
    agent_id: UUID
    status: str
    started_at: datetime
    speaking_role: str | None = None
    last_interruption_at: datetime | None = None


class ActiveSessionStore(Protocol):
    """Fast, ephemeral store of the sessions currently in progress (R7).

    Written best-effort during ingestion; a failure here must never break ingestion.
    """

    async def mark_active(self, snapshot: ActiveSessionSnapshot) -> None: ...

    async def upsert_lifecycle(self, snapshot: ActiveSessionSnapshot) -> None: ...

    async def mark_ended(self, session_id: str) -> None: ...

    async def list_active(self) -> list[ActiveSessionSnapshot]: ...

    async def set_speaking_role(self, session_id: str, role: str | None) -> None: ...

    async def mark_interruption(self, session_id: str, at: datetime) -> None: ...
