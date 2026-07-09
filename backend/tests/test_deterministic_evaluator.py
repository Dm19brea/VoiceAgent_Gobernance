"""M4.4-M4.5 — DeterministicEvaluator: evidences -> report (spec S4-S8)."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from src.domain.enums import EvaluationResult, EventType, Source
from src.domain.evaluation_report import EvaluationReport
from src.domain.evidence_builder import build_evidences
from src.domain.scoring.evaluator import DeterministicEvaluator
from src.domain.scoring.flags import FLAG_SESSION_FAILED, FLAG_SESSION_NOT_COMPLETED
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
) -> Session:
    session = _open_session(agent_turns=agent_turns, user_turns=user_turns)
    end = START + timedelta(seconds=duration_seconds)
    session.record(EventType.SESSION_ENDED, Source.PLATFORM, end, {"report": report or {}})
    return session


def _failed_session(
    *,
    agent_turns: int = 1,
    user_turns: int = 1,
    duration_seconds: int = 47,
    report: dict[str, Any] | None = None,
) -> Session:
    session = _open_session(agent_turns=agent_turns, user_turns=user_turns)
    end = START + timedelta(seconds=duration_seconds)
    session.record(EventType.SESSION_FAILED, Source.PLATFORM, end, {"report": report or {}})
    return session


def _evaluate(session: Session) -> EvaluationReport:
    return DeterministicEvaluator().evaluate(session, build_evidences(session))


def test_failed_session_raises_flag_session_failed_and_result_is_failed() -> None:
    report = _evaluate(
        _failed_session(report={"ended_reason": "pipeline-error-openai-llm-failed"})
    )

    assert report.result is EvaluationResult.FAILED
    assert [flag.code for flag in report.blocking_flags] == [FLAG_SESSION_FAILED]


def test_blocking_flag_forces_failed_despite_high_score() -> None:  # S4
    # Active session, both sides speak -> engagement 100 -> global 100, but never completed.
    report = _evaluate(_open_session(agent_turns=2, user_turns=2))

    assert report.score_global == 100
    assert report.result is EvaluationResult.FAILED
    assert report.blocking_flags[0].code == FLAG_SESSION_NOT_COMPLETED


def test_high_score_without_flags_passes() -> None:  # S5
    report = _evaluate(_closed_session(report={"ended_reason": "customer-ended-call"}))

    assert report.score_global >= 75
    assert report.blocking_flags == []
    assert report.result is EvaluationResult.PASSED


def test_report_carries_scores_result_and_metrics_snapshot() -> None:  # S6
    report = _evaluate(_closed_session(report={"ended_reason": "customer-ended-call"}))

    assert report.session_id == "call-1"
    assert report.score_global is not None
    assert report.score_conversational is not None
    assert report.score_technical is not None
    assert report.score_risk is not None
    assert {m.code for m in report.metrics} == {
        "engagement",
        "completion",
        "duration",
        "clean_ending",
    }


def test_operational_dimension_is_excluded_when_it_has_no_metrics() -> None:  # S8
    report = _evaluate(_closed_session(report={"ended_reason": "customer-ended-call"}))

    assert report.score_operational is None


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
