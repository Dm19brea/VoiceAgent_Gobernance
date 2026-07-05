"""M4.1 — Metric value object + dimension/global scoring (spec S2, S3)."""

import pytest

from src.domain.enums import Dimension
from src.domain.scoring.engine import dimension_score, global_score
from src.domain.scoring.metric import Metric


def _metric(
    *,
    dimension: Dimension = Dimension.TECHNICAL,
    normalized_score: float = 100,
    weight: float = 1,
    code: str = "m",
) -> Metric:
    return Metric(
        code=code,
        dimension=dimension,
        raw_value=1,
        normalized_score=normalized_score,
        weight=weight,
        unit="bool",
    )


def test_dimension_score_is_weighted_mean_of_metric_scores() -> None:
    metrics = [
        _metric(code="a", normalized_score=100, weight=3),
        _metric(code="b", normalized_score=0, weight=1),
    ]

    # (100*3 + 0*1) / (3 + 1) = 75
    assert dimension_score(metrics) == 75


def test_dimension_score_of_single_metric_is_its_score() -> None:
    assert dimension_score([_metric(normalized_score=80)]) == 80


def test_global_score_weights_dimensions_by_their_weight() -> None:
    scores = {
        Dimension.CONVERSATIONAL: 100,
        Dimension.TECHNICAL: 50,
        Dimension.RISK: 0,
    }

    # weights conversational 3, technical 2, risk 4:
    # (100*3 + 50*2 + 0*4) / (3 + 2 + 4) = 400 / 9
    assert global_score(scores) == pytest.approx(44.44, abs=0.01)


def test_global_score_excludes_dimensions_without_a_score() -> None:
    assert global_score({Dimension.TECHNICAL: 80}) == 80
