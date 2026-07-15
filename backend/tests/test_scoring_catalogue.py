"""M4.3 — Metric catalogue: build_metrics from a session's evidences (D1/D2, R1/R10)."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest

from src.domain.enums import Dimension, EventType, EvidenceType, Source
from src.domain.evidence import Evidence
from src.domain.evidence_builder import build_evidences
from src.domain.scoring.catalogue import build_metrics
from src.domain.scoring.metric import Metric
from src.domain.session import Session

START = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)


def _session(
    *,
    agent_turns: int = 1,
    user_turns: int = 1,
    duration_seconds: int = 47,
    report: dict[str, Any] | None = None,
    failed: bool = False,
    goal_achieved: bool | None = None,
    flag_count: int = 0,
    warnings: int = 0,
    errors: int = 0,
    silences: int = 0,
    interruptions: int = 0,
) -> Session:
    session = Session.open("call-1", uuid4(), START)
    session.record(EventType.SESSION_STARTED, Source.PLATFORM, START, {})
    for _ in range(agent_turns):
        session.record(EventType.CONVERSATION_AGENT_RESPONSE, Source.AGENT, START, {})
    for _ in range(user_turns):
        session.record(EventType.CONVERSATION_USER_INPUT, Source.USER, START, {})
    for _ in range(interruptions):
        session.record(EventType.CONVERSATION_INTERRUPTION_DETECTED, Source.SYSTEM, START, {})
    if goal_achieved is True:
        session.record(EventType.CONVERSATION_GOAL_ACHIEVED, Source.SYSTEM, START, {})
    elif goal_achieved is False:
        session.record(EventType.CONVERSATION_GOAL_FAILED, Source.SYSTEM, START, {})
    for _ in range(warnings):
        session.record(EventType.SYSTEM_WARNING, Source.SYSTEM, START, {})
    for _ in range(errors):
        session.record(EventType.SYSTEM_ERROR, Source.SYSTEM, START, {})
    if silences:
        session.record(
            EventType.CONVERSATION_SILENCE_DETECTED, Source.SYSTEM, START, {"count": silences}
        )
    for _ in range(flag_count):
        session.record(EventType.SYSTEM_FLAG_RAISED, Source.SYSTEM, START, {})
    end = START + timedelta(seconds=duration_seconds)
    event_type = EventType.SESSION_FAILED if failed else EventType.SESSION_ENDED
    session.record(event_type, Source.PLATFORM, end, {"report": report or {}})
    return session


def _closed_session(**kwargs: Any) -> Session:
    return _session(**kwargs)


def _failed_session(**kwargs: Any) -> Session:
    return _session(failed=True, **kwargs)


def _metrics(session: Session) -> dict[str, Metric]:
    return {m.code: m for m in build_metrics(session, build_evidences(session))}


def _evidence(
    criterion: str, value: float | None, *, dimension: Dimension = Dimension.RISK
) -> Evidence:
    return Evidence(
        session_id="call-1",
        evidence_type=EvidenceType.INFERRED,
        criterion=criterion,
        conclusion="test evidence",
        dimension=dimension,
        source_events=[],
        value=value,
    )


def test_full_session_yields_the_legacy_and_spec_metrics() -> None:
    metrics = _metrics(_closed_session(report={"ended_reason": "customer-ended-call"}))

    assert {"engagement", "duration"}.issubset(metrics)
    assert "completion" not in metrics
    assert "clean_ending" not in metrics
    assert metrics["engagement"].dimension is Dimension.CONVERSATIONAL
    assert metrics["duration"].dimension is Dimension.TECHNICAL


def test_engagement_is_full_when_both_sides_speak() -> None:
    metrics = _metrics(_closed_session(agent_turns=2, user_turns=2))

    assert metrics["engagement"].normalized_score == 100
    assert metrics["engagement"].weight == 3


def test_engagement_is_zero_when_one_side_is_silent() -> None:
    metrics = _metrics(_closed_session(agent_turns=2, user_turns=0))

    assert metrics["engagement"].normalized_score == 0


def test_duration_uses_latency_normalisation() -> None:
    # 600s with optimal=300, degraded=900 -> (900-600)/(900-300) = 0.5 -> 50
    metrics = _metrics(_closed_session(duration_seconds=600))

    assert metrics["duration"].raw_value == 600
    assert metrics["duration"].normalized_score == 50


# -- M-R01 governance_flag_count (occurrences sanity, doc worked example) -----------------


@pytest.mark.parametrize(
    ("flag_count", "expected_score"),
    [(0, 100), (1, 67), (2, 34)],
)
def test_m_r01_occurrences_sanity(flag_count: int, expected_score: float) -> None:
    metrics = _metrics(_closed_session(flag_count=flag_count))

    assert metrics["M-R01"].normalized_score == expected_score
    assert metrics["M-R01"].weight == 3
    assert metrics["M-R01"].dimension is Dimension.RISK


def test_m_r01_is_omitted_when_its_evidence_is_absent() -> None:
    session = Session.open("call-1", uuid4(), START)

    metrics = {m.code for m in build_metrics(session, [])}

    assert "M-R01" not in metrics


def test_m_r01_is_omitted_when_its_evidence_value_is_none() -> None:
    session = Session.open("call-1", uuid4(), START)
    evidences = [_evidence("governance_flag_count", None)]

    metrics = {m.code for m in build_metrics(session, evidences)}

    assert "M-R01" not in metrics


# -- Risk dimension: M-R02, M-R04 ----------------------------------------------------------


@pytest.mark.parametrize(("errors", "failed", "expected_score"), [(0, False, 100), (1, True, 0)])
def test_m_r02_unrecovered_error_present_is_inversely_scored(
    errors: int, failed: bool, expected_score: float
) -> None:
    metrics = _metrics(_session(errors=errors, failed=failed))

    assert metrics["M-R02"].normalized_score == expected_score
    assert metrics["M-R02"].weight == 3
    assert metrics["M-R02"].dimension is Dimension.RISK
    assert metrics["M-R02"].code == "M-R02"


def test_m_r04_system_warning_rate_rescales_before_normalising() -> None:
    # 1 warning out of agent(1)+user(1)=2 turns -> rate 0.5 -> ×100=50 -> inverse -> 50
    metrics = _metrics(_closed_session(warnings=1))

    assert metrics["M-R04"].normalized_score == 50
    assert metrics["M-R04"].weight == 1
    assert metrics["M-R04"].dimension is Dimension.RISK


# -- Conversational dimension: M-C01, M-C02, M-C03 ------------------------------------------


def test_m_c01_turn_completion_rate_does_not_collapse_near_zero() -> None:
    # 1 agent turn, 0 interruptions -> rate 1.0 -> ×100=100 -> percentage_direct -> 100
    metrics = _metrics(_closed_session(agent_turns=1, interruptions=0))

    assert metrics["M-C01"].normalized_score == 100
    assert metrics["M-C01"].weight == 2


def test_m_c02_prolonged_silence_rate_is_percentage_inverse() -> None:
    # 1 silence out of agent(1)+user(1)=2 turns -> rate 0.5 -> ×100=50 -> inverse -> 50
    metrics = _metrics(_closed_session(silences=1))

    assert metrics["M-C02"].normalized_score == 50
    assert metrics["M-C02"].weight == 1


@pytest.mark.parametrize(("goal_achieved", "expected_score"), [(True, 100), (False, 0)])
def test_m_c03_goal_completion_is_binary(goal_achieved: bool, expected_score: float) -> None:
    metrics = _metrics(_closed_session(goal_achieved=goal_achieved))

    assert metrics["M-C03"].normalized_score == expected_score
    assert metrics["M-C03"].weight == 4


def test_m_c03_is_omitted_when_no_goal_signal_exists() -> None:
    # No explicit conversation.goal_achieved/goal_failed signal exists, so
    # goal_completion evidence is never built and M-C03 is omitted (spec R2, R10).
    metrics = _metrics(_closed_session(goal_achieved=None))

    assert "M-C03" not in metrics


# -- Technical dimension: M-T03, M-T04 -------------------------------------------------------


def test_m_t03_technical_error_rate_rescales_before_normalising() -> None:
    # 1 error out of agent(1)+user(1)=2 turns -> rate 0.5 -> ×100=50 -> inverse -> 50
    metrics = _metrics(_closed_session(errors=1))

    assert metrics["M-T03"].normalized_score == 50
    assert metrics["M-T03"].weight == 3


def test_m_t04_model_invocation_count_is_informational_weight_zero() -> None:
    metrics = _metrics(_closed_session())

    assert metrics["M-T04"].weight == 0
    assert metrics["M-T04"].normalized_score == 100


# -- Technical dimension: M-T01, M-T02 latency ------------------------------------------------


def test_m_t01_and_m_t02_latency_sanity() -> None:
    report = {"turn_latencies_seconds": [2.0]}
    metrics = _metrics(_closed_session(report=report))

    assert metrics["M-T01"].normalized_score == 67  # mean=2.0 -> latency(2.0,1.5,3.0)
    assert metrics["M-T01"].weight == 3
    assert metrics["M-T02"].normalized_score == 100  # max=2.0 <= optimal(3.0) -> full score


def test_m_t02_uses_the_max_latency_value() -> None:
    report = {"turn_latencies_seconds": [1.0, 4.0]}
    metrics = _metrics(_closed_session(report=report))

    assert metrics["M-T02"].normalized_score == 50  # max=4.0 -> latency(4.0,3.0,5.0)
    assert metrics["M-T02"].weight == 2


def test_m_t01_and_m_t02_are_omitted_when_report_has_no_latency_data() -> None:
    metrics = _metrics(_closed_session(report={"ended_reason": "customer-ended-call"}))

    assert "M-T01" not in metrics
    assert "M-T02" not in metrics


def test_m_t01_and_m_t02_use_seconds_directly_without_reconverting() -> None:
    # Guards against reintroducing ms->s conversion inside the catalogue: the Vapi
    # mapping boundary already converts once, so report values reaching evidence and
    # scoring here are already seconds (spec R3, design "canonical unit").
    report = {"turn_latencies_seconds": [3.010714, 7.234]}
    metrics = _metrics(_closed_session(report=report))

    assert metrics["M-T01"].raw_value == pytest.approx((3.010714 + 7.234) / 2)
    assert metrics["M-T02"].raw_value == pytest.approx(7.234)


def test_tool_metrics_are_not_in_the_scoring_catalogue() -> None:
    assert all(metric.code != "M-O04" for metric in _metrics(_closed_session()).values())


# -- Legacy retirement -------------------------------------------------------------------------


def test_completion_and_clean_ending_are_never_emitted() -> None:
    for session in (
        _closed_session(report={"ended_reason": "customer-ended-call"}),
        _failed_session(report={"ended_reason": "pipeline-error-openai-llm-failed"}),
    ):
        codes = {m.code for m in build_metrics(session, build_evidences(session))}
        assert "completion" not in codes
        assert "clean_ending" not in codes


def test_build_metrics_omits_metrics_when_no_evidence_is_given() -> None:
    session = Session.open("call-2", uuid4(), START)

    metrics = build_metrics(session, [])

    assert metrics == []


def test_build_metrics_is_deterministic() -> None:
    session = _closed_session(report={"ended_reason": "assistant-ended-call"})
    evidences = build_evidences(session)

    first = build_metrics(session, evidences)
    second = build_metrics(session, evidences)

    assert first == second
