"""M4.4-M4.5 — DeterministicEvaluator: evidences -> report (spec S4-S17)."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from src.domain.enums import EvaluationResult, EventType, Source
from src.domain.evaluation_report import EvaluationReport
from src.domain.evidence_builder import build_evidences
from src.domain.scoring.evaluator import DeterministicEvaluator
from src.domain.scoring.flags import (
    FLAG_GOAL_NOT_COMPLETED,
    FLAG_SESSION_FAILED,
    FLAG_SESSION_NOT_COMPLETED,
    FLAG_UNRECOVERED_ERROR,
)
from src.domain.session import Session

START = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)


def _open_session(*, agent_turns: int = 1, user_turns: int = 1) -> Session:
    session = Session.open("call-1", uuid4(), START)
    session.record(EventType.SESSION_STARTED, Source.PLATFORM, START, {})
    for _ in range(agent_turns):
        session.record(EventType.CONVERSATION_AGENT_RESPONSE, Source.AGENT, START, {})
    for _ in range(user_turns):
        session.record(EventType.CONVERSATION_USER_INPUT, Source.USER, START, {})
    return session


def _closed_session(
    *,
    agent_turns: int = 1,
    user_turns: int = 1,
    duration_seconds: int = 47,
    report: dict[str, Any] | None = None,
    goal_achieved: bool = True,
) -> Session:
    session = _open_session(agent_turns=agent_turns, user_turns=user_turns)
    session.record(EventType.CONVERSATION_GOAL_ACHIEVED, Source.SYSTEM, START, {})
    if not goal_achieved:
        session.events.pop()
        session.record(EventType.CONVERSATION_GOAL_FAILED, Source.SYSTEM, START, {})
    end = START + timedelta(seconds=duration_seconds)
    session.record(EventType.SESSION_ENDED, Source.PLATFORM, end, {"report": report or {}})
    return session


def _failed_session(
    *,
    agent_turns: int = 1,
    user_turns: int = 1,
    duration_seconds: int = 47,
    report: dict[str, Any] | None = None,
    with_error: bool = True,
) -> Session:
    session = _open_session(agent_turns=agent_turns, user_turns=user_turns)
    if with_error:
        session.record(EventType.SYSTEM_ERROR, Source.SYSTEM, START, {})
    end = START + timedelta(seconds=duration_seconds)
    session.record(EventType.SESSION_FAILED, Source.PLATFORM, end, {"report": report or {}})
    return session


def _evaluate(session: Session) -> EvaluationReport:
    return DeterministicEvaluator().evaluate(session, build_evidences(session))


def test_failed_session_with_error_raises_session_failed_and_unrecovered_error() -> None:
    report = _evaluate(_failed_session(report={"ended_reason": "pipeline-error-openai-llm-failed"}))

    assert report.result is EvaluationResult.FAILED
    codes = {flag.code for flag in report.blocking_flags}
    assert FLAG_SESSION_FAILED in codes
    assert FLAG_UNRECOVERED_ERROR in codes  # co-occurs, no suppression (design D5)


def test_blocking_flag_forces_failed_despite_a_never_completed_session() -> None:  # S4
    report = _evaluate(_open_session(agent_turns=2, user_turns=2))

    assert report.result is EvaluationResult.FAILED
    codes = {flag.code for flag in report.blocking_flags}
    assert FLAG_SESSION_NOT_COMPLETED in codes
    assert FLAG_GOAL_NOT_COMPLETED in codes  # no goal event recorded -> orthogonal flag also fires


def test_high_score_without_flags_passes() -> None:  # S5
    report = _evaluate(_closed_session(report={"ended_reason": "customer-ended-call"}))

    assert report.score_global >= 75
    assert report.blocking_flags == []
    assert report.result is EvaluationResult.PASSED


def test_goal_not_completed_flag_fires_even_on_a_clean_ending() -> None:
    report = _evaluate(
        _closed_session(report={"ended_reason": "customer-ended-call"}, goal_achieved=False)
    )

    codes = {flag.code for flag in report.blocking_flags}
    assert FLAG_GOAL_NOT_COMPLETED in codes
    assert report.result is EvaluationResult.FAILED


def test_report_carries_scores_result_and_metrics_snapshot() -> None:  # S6
    report = _evaluate(_closed_session(report={"ended_reason": "customer-ended-call"}))

    assert report.session_id == "call-1"
    assert report.score_global is not None
    assert report.score_conversational is not None
    assert report.score_technical is not None
    assert report.score_risk is not None
    codes = {m.code for m in report.metrics}
    assert {"engagement", "duration", "M-C01", "M-C02", "M-C03", "M-T03", "M-T04"}.issubset(codes)
    assert "completion" not in codes
    assert "clean_ending" not in codes


def test_operational_dimension_is_excluded_when_only_weight_zero_metrics_exist() -> None:  # S8
    # M-O04 (tool_usage_density) is the only OPERATIONAL metric and has weight 0.
    report = _evaluate(_closed_session(report={"ended_reason": "customer-ended-call"}))

    assert report.score_operational is None
    assert any(m.code == "M-O04" for m in report.metrics)  # present in the snapshot regardless


def test_informational_metrics_never_move_the_dimension_score() -> None:
    with_tool_calls = _evaluate(_closed_session(report={"ended_reason": "customer-ended-call"}))
    without = _evaluate(_closed_session(report={"ended_reason": "customer-ended-call"}))

    assert with_tool_calls.score_technical == without.score_technical
    assert with_tool_calls.score_operational == without.score_operational is None


def test_high_technical_error_rate_lowers_technical_and_global_score() -> None:
    low_error = _evaluate(_closed_session(report={"ended_reason": "customer-ended-call"}))

    high_error_session = _open_session(agent_turns=2, user_turns=2)
    high_error_session.record(EventType.CONVERSATION_GOAL_ACHIEVED, Source.SYSTEM, START, {})
    for _ in range(4):
        high_error_session.record(EventType.SYSTEM_ERROR, Source.SYSTEM, START, {})
    high_error_session.record(
        EventType.SESSION_ENDED,
        Source.PLATFORM,
        START + timedelta(seconds=47),
        {"report": {"ended_reason": "customer-ended-call"}},
    )
    high_error = _evaluate(high_error_session)

    assert high_error.score_technical is not None
    assert low_error.score_technical is not None
    assert high_error.score_technical < low_error.score_technical
    assert high_error.score_global < low_error.score_global


def test_evaluation_is_deterministic() -> None:  # S7
    session = _closed_session(report={"ended_reason": "assistant-ended-call"})
    evidences = build_evidences(session)
    evaluator = DeterministicEvaluator()

    first = evaluator.evaluate(session, evidences)
    second = evaluator.evaluate(session, evidences)

    def _content(report: EvaluationReport) -> tuple[Any, ...]:
        return (
            report.score_global,
            report.result,
            report.score_conversational,
            report.score_technical,
            report.score_risk,
            [(m.code, m.normalized_score) for m in report.metrics],
            [f.code for f in report.blocking_flags],
        )

    assert _content(first) == _content(second)


def test_session_with_no_evidences_does_not_crash() -> None:  # S8
    session = Session.open("call-2", uuid4(), START)

    report = DeterministicEvaluator().evaluate(session, [])

    assert report.score_global == 0
    assert report.metrics == []
    assert report.result is EvaluationResult.FAILED
