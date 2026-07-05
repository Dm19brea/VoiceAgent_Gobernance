"""Deterministic evaluator: a session's evidences -> EvaluationReport (design D5, D6).

Pure and reproducible: given the same evidences it always yields the same report content
(except ``report_id`` and ``generated_at``). A future LLM-judge can implement the same
``evaluate`` shape without touching this domain code.
"""

from collections import defaultdict
from collections.abc import Sequence

from src.domain.enums import Dimension, EvaluationResult
from src.domain.evaluation_report import EvaluationReport
from src.domain.evidence import Evidence
from src.domain.scoring.catalogue import build_metrics
from src.domain.scoring.engine import dimension_score, global_score
from src.domain.scoring.flags import BlockingFlag, detect_blocking_flags
from src.domain.scoring.metric import Metric
from src.domain.session import Session

PASS_THRESHOLD = 75.0


class DeterministicEvaluator:
    """The doc 3.4 scoring model: normalise -> aggregate -> global -> flags -> result."""

    def evaluate(self, session: Session, evidences: Sequence[Evidence]) -> EvaluationReport:
        metrics = build_metrics(session, evidences)
        dimension_scores = _score_by_dimension(metrics)
        score = global_score(dimension_scores) if dimension_scores else 0.0
        flags = detect_blocking_flags(evidences)

        return EvaluationReport(
            session_id=session.session_id,
            score_global=score,
            result=_result(score, flags),
            score_conversational=dimension_scores.get(Dimension.CONVERSATIONAL),
            score_operational=dimension_scores.get(Dimension.OPERATIONAL),
            score_technical=dimension_scores.get(Dimension.TECHNICAL),
            score_risk=dimension_scores.get(Dimension.RISK),
            blocking_flags=flags,
            metrics=metrics,
        )


def _score_by_dimension(metrics: Sequence[Metric]) -> dict[Dimension, float]:
    grouped: dict[Dimension, list[Metric]] = defaultdict(list)
    for metric in metrics:
        grouped[metric.dimension].append(metric)
    return {dimension: dimension_score(group) for dimension, group in grouped.items()}


def _result(score: float, flags: Sequence[BlockingFlag]) -> EvaluationResult:
    if flags or score < PASS_THRESHOLD:
        return EvaluationResult.FAILED
    return EvaluationResult.PASSED
