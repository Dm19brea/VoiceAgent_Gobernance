"""Pure scoring aggregation: metrics -> dimension scores -> global score (doc 3.4.3-3.4.4)."""

from collections.abc import Mapping, Sequence

from src.domain.enums import Dimension
from src.domain.scoring.metric import Metric

# Default dimension weights (doc 3.4.4). Operational is defined but excluded from
# scoring while no operational metrics exist; missing dimensions never contribute.
DIMENSION_WEIGHTS: dict[Dimension, float] = {
    Dimension.CONVERSATIONAL: 3.0,
    Dimension.OPERATIONAL: 3.0,
    Dimension.TECHNICAL: 2.0,
    Dimension.RISK: 4.0,
}


def dimension_score(metrics: Sequence[Metric]) -> float:
    """Weighted mean of the normalised scores of a dimension's metrics (R3).

    Callers exclude empty dimensions from scoring; this expects at least one metric.
    """
    total_weight = sum(metric.weight for metric in metrics)
    weighted = sum(metric.normalized_score * metric.weight for metric in metrics)
    return weighted / total_weight


def global_score(dimension_scores: Mapping[Dimension, float]) -> float:
    """Weighted mean of dimension scores using dimension weights (R4).

    Only the dimensions present in ``dimension_scores`` contribute; excluded
    dimensions do not affect the result.
    """
    total_weight = sum(DIMENSION_WEIGHTS[dimension] for dimension in dimension_scores)
    weighted = sum(
        score * DIMENSION_WEIGHTS[dimension]
        for dimension, score in dimension_scores.items()
    )
    return weighted / total_weight
