from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from src.domain.enums import EvaluationResult
from src.domain.scoring.flags import BlockingFlag
from src.domain.scoring.metric import Metric


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    """Immutable outcome of evaluating a session's evidences (doc 3.3, design D5, R7).

    Per-dimension scores are nullable: a dimension with no metrics is excluded from
    scoring rather than scored zero.
    """

    session_id: str
    score_global: float
    result: EvaluationResult
    score_conversational: float | None = None
    score_operational: float | None = None
    score_technical: float | None = None
    score_risk: float | None = None
    blocking_flags: list[BlockingFlag] = field(default_factory=list)
    metrics: list[Metric] = field(default_factory=list)
    report_id: UUID = field(default_factory=uuid4)
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
