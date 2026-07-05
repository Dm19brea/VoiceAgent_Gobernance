from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from src.domain.enums import Dimension, EvidenceType


@dataclass(frozen=True, slots=True)
class Evidence:
    """A verifiable claim about an agent's behaviour, grounded in real events (doc 3.2)."""

    session_id: str
    evidence_type: EvidenceType
    criterion: str
    conclusion: str
    dimension: Dimension
    source_events: list[UUID]
    value: float | None = None
    evidence_id: UUID = field(default_factory=uuid4)
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
