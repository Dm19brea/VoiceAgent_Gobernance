"""M4.4 — EvaluationResult enum + EvaluationReport frozen entity (design D5, spec R7)."""

import dataclasses

import pytest

from src.domain.enums import Dimension, EvaluationResult
from src.domain.evaluation_report import EvaluationReport
from src.domain.scoring.flags import BlockingFlag
from src.domain.scoring.metric import Metric


def _metric() -> Metric:
    return Metric(
        code="completion",
        dimension=Dimension.TECHNICAL,
        raw_value=1.0,
        normalized_score=100,
        weight=3.0,
        unit="bool",
    )


def test_evaluation_result_has_passed_and_failed() -> None:
    assert EvaluationResult.PASSED == "passed"
    assert EvaluationResult.FAILED == "failed"


def test_report_holds_scores_result_flags_and_metrics() -> None:
    report = EvaluationReport(
        session_id="call-1",
        score_global=82.5,
        result=EvaluationResult.PASSED,
        score_technical=100,
        metrics=[_metric()],
    )

    assert report.session_id == "call-1"
    assert report.score_global == 82.5
    assert report.result is EvaluationResult.PASSED
    assert report.score_technical == 100
    assert report.metrics[0].code == "completion"
    assert report.blocking_flags == []


def test_report_generates_id_and_timestamp() -> None:
    report = EvaluationReport(
        session_id="call-1",
        score_global=0,
        result=EvaluationResult.FAILED,
    )

    assert report.report_id is not None
    assert report.generated_at is not None


def test_dimension_scores_default_to_none() -> None:
    report = EvaluationReport(
        session_id="call-1",
        score_global=0,
        result=EvaluationResult.FAILED,
    )

    assert report.score_conversational is None
    assert report.score_operational is None
    assert report.score_technical is None
    assert report.score_risk is None


def test_report_carries_blocking_flags() -> None:
    flag = BlockingFlag(code="session_not_completed", reason="No completion event.")
    report = EvaluationReport(
        session_id="call-1",
        score_global=90,
        result=EvaluationResult.FAILED,
        blocking_flags=[flag],
    )

    assert report.blocking_flags == [flag]


def test_report_is_immutable() -> None:
    report = EvaluationReport(
        session_id="call-1",
        score_global=0,
        result=EvaluationResult.FAILED,
    )

    with pytest.raises(dataclasses.FrozenInstanceError):
        report.score_global = 100  # type: ignore[misc]
