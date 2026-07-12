from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from src.domain.enums import Dimension, EventType, EvidenceType, Source
from src.domain.evidence import Evidence
from src.domain.evidence_builder import build_evidences
from src.domain.session import Session

START = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
END = datetime(2026, 1, 1, 10, 0, 47, tzinfo=UTC)


def _closed_session(report: dict[str, Any] | None = None) -> Session:
    session = Session.open("call-1", uuid4(), START)
    session.record(EventType.SESSION_STARTED, Source.PLATFORM, START, {})
    session.record(EventType.CONVERSATION_AGENT_RESPONSE, Source.AGENT, START, {})
    session.record(EventType.CONVERSATION_USER_INPUT, Source.USER, START, {})
    session.record(EventType.SESSION_ENDED, Source.PLATFORM, END, {"report": report or {}})
    return session


def _failed_session(report: dict[str, Any] | None = None) -> Session:
    session = Session.open("call-1", uuid4(), START)
    session.record(EventType.SESSION_STARTED, Source.PLATFORM, START, {})
    session.record(EventType.CONVERSATION_AGENT_RESPONSE, Source.AGENT, START, {})
    session.record(EventType.CONVERSATION_USER_INPUT, Source.USER, START, {})
    session.record(EventType.SESSION_FAILED, Source.PLATFORM, END, {"report": report or {}})
    return session


def _by_criterion(evidences: list[Evidence]) -> dict[str, Evidence]:
    return {e.criterion: e for e in evidences}


def test_builds_turn_evidences() -> None:
    evidences = _by_criterion(build_evidences(_closed_session()))

    assert evidences["total_turns"].value == 2.0
    assert evidences["agent_turns"].value == 1.0
    assert evidences["user_turns"].value == 1.0
    assert evidences["total_turns"].dimension is Dimension.CONVERSATIONAL
    assert len(evidences["total_turns"].source_events) == 2


def test_builds_duration_evidence() -> None:
    evidences = _by_criterion(build_evidences(_closed_session()))

    duration = evidences["session_duration_seconds"]
    assert duration.value == 47.0
    assert duration.evidence_type is EvidenceType.INFERRED
    assert duration.dimension is Dimension.TECHNICAL


def test_builds_session_completed_evidence() -> None:
    evidences = _by_criterion(build_evidences(_closed_session()))

    completed = evidences["session_completed"]
    assert completed.evidence_type is EvidenceType.DIRECT
    assert completed.dimension is Dimension.TECHNICAL


def test_builds_ended_reason_from_report() -> None:
    evidences = _by_criterion(
        build_evidences(_closed_session(report={"ended_reason": "customer-ended-call"}))
    )

    reason = evidences["ended_reason"]
    assert reason.evidence_type is EvidenceType.DIRECT
    assert "customer-ended-call" in reason.conclusion


def test_missing_ended_reason_does_not_crash() -> None:
    evidences = _by_criterion(build_evidences(_closed_session(report={})))

    assert "ended_reason" not in evidences
    assert "session_completed" in evidences


def test_failed_session_yields_session_failed_criterion_not_completed() -> None:
    evidences = _by_criterion(
        build_evidences(
            _failed_session(report={"ended_reason": "pipeline-error-openai-llm-failed"})
        )
    )

    assert "session_completed" not in evidences
    failed = evidences["session_failed"]
    assert failed.evidence_type is EvidenceType.DIRECT
    assert failed.dimension is Dimension.TECHNICAL
    assert failed.conclusion == "The session failed"


def test_failed_session_still_yields_ended_reason_evidence() -> None:
    evidences = _by_criterion(
        build_evidences(
            _failed_session(report={"ended_reason": "pipeline-error-openai-llm-failed"})
        )
    )

    reason = evidences["ended_reason"]
    assert reason.evidence_type is EvidenceType.DIRECT
    assert "pipeline-error-openai-llm-failed" in reason.conclusion


def test_failed_session_duration_evidence_includes_terminal_event() -> None:
    session = _failed_session(report={"ended_reason": "pipeline-error-openai-llm-failed"})
    terminal_event = session.events[-1]

    evidences = _by_criterion(build_evidences(session))

    duration = evidences["session_duration_seconds"]
    assert terminal_event.event_id in duration.source_events


def _summary(evidences: list[Evidence]) -> dict[str, tuple[str, float | None]]:
    return {e.criterion: (e.conclusion, e.value) for e in evidences}


def test_build_evidences_is_deterministic() -> None:
    session = _closed_session(report={"ended_reason": "assistant-ended-call"})

    first = build_evidences(session)
    second = build_evidences(session)

    assert _summary(first) == _summary(second)


def _session_with_events(*extra: tuple[EventType, Source, dict[str, Any]]) -> Session:
    session = Session.open("call-1", uuid4(), START)
    session.record(EventType.SESSION_STARTED, Source.PLATFORM, START, {})
    for event_type, source, payload in extra:
        session.record(event_type, source, START, payload)
    session.record(EventType.SESSION_ENDED, Source.PLATFORM, END, {})
    return session


def test_goal_achieved_yields_goal_completion_evidence() -> None:
    session = _session_with_events((EventType.CONVERSATION_GOAL_ACHIEVED, Source.SYSTEM, {}))
    goal_event = session.events[1]

    evidences = _by_criterion(build_evidences(session))

    goal = evidences["goal_completion"]
    assert goal.value == pytest.approx(1.0)
    assert goal.evidence_type is EvidenceType.INFERRED
    assert goal.dimension is Dimension.CONVERSATIONAL
    assert goal_event.event_id in goal.source_events


def test_goal_failed_yields_zero_goal_completion_evidence() -> None:
    session = _session_with_events((EventType.CONVERSATION_GOAL_FAILED, Source.SYSTEM, {}))
    goal_event = session.events[1]

    evidences = _by_criterion(build_evidences(session))

    goal = evidences["goal_completion"]
    assert goal.value == pytest.approx(0.0)
    assert goal_event.event_id in goal.source_events


def test_no_goal_event_yields_zero_goal_completion_with_empty_source_events() -> None:
    session = _session_with_events()

    evidences = _by_criterion(build_evidences(session))

    goal = evidences["goal_completion"]
    assert goal.value == pytest.approx(0.0)
    assert goal.source_events == []


def test_turn_completion_rate_accounts_for_interruptions() -> None:
    session = _session_with_events(
        *[(EventType.CONVERSATION_AGENT_RESPONSE, Source.AGENT, {}) for _ in range(4)],
        (EventType.CONVERSATION_INTERRUPTION_DETECTED, Source.SYSTEM, {}),
    )

    evidences = _by_criterion(build_evidences(session))

    rate = evidences["turn_completion_rate"]
    assert rate.value == pytest.approx(0.75)
    assert rate.evidence_type is EvidenceType.INFERRED
    assert rate.dimension is Dimension.CONVERSATIONAL


def test_turn_completion_rate_is_one_without_interruptions() -> None:
    session = _session_with_events(
        *[(EventType.CONVERSATION_AGENT_RESPONSE, Source.AGENT, {}) for _ in range(3)],
    )

    evidences = _by_criterion(build_evidences(session))

    assert evidences["turn_completion_rate"].value == pytest.approx(1.0)


def test_turn_completion_rate_zero_denominator_guard() -> None:
    session = _session_with_events()

    evidences = _by_criterion(build_evidences(session))

    rate = evidences["turn_completion_rate"]
    assert rate.value == pytest.approx(0.0)
    assert "agent" in rate.conclusion.lower()


def test_prolonged_silence_rate_with_aggregated_event() -> None:
    session = _session_with_events(
        *[(EventType.CONVERSATION_AGENT_RESPONSE, Source.AGENT, {}) for _ in range(4)],
        *[(EventType.CONVERSATION_USER_INPUT, Source.USER, {}) for _ in range(4)],
        (EventType.CONVERSATION_SILENCE_DETECTED, Source.PLATFORM, {"count": 2}),
    )

    evidences = _by_criterion(build_evidences(session))

    rate = evidences["prolonged_silence_rate"]
    assert rate.value == pytest.approx(0.25)
    assert rate.evidence_type is EvidenceType.INFERRED
    assert rate.dimension is Dimension.CONVERSATIONAL


def test_prolonged_silence_rate_zero_without_silence_event() -> None:
    session = _session_with_events(
        *[(EventType.CONVERSATION_AGENT_RESPONSE, Source.AGENT, {}) for _ in range(2)],
        *[(EventType.CONVERSATION_USER_INPUT, Source.USER, {}) for _ in range(2)],
    )

    evidences = _by_criterion(build_evidences(session))

    rate = evidences["prolonged_silence_rate"]
    assert rate.value == pytest.approx(0.0)
    assert rate.source_events == []


def test_prolonged_silence_rate_zero_denominator_guard() -> None:
    session = _session_with_events()

    evidences = _by_criterion(build_evidences(session))

    rate = evidences["prolonged_silence_rate"]
    assert rate.value == pytest.approx(0.0)
    assert "turn" in rate.conclusion.lower()


def test_mvp_turn_evidences_unaffected_by_new_conversational_evidences() -> None:
    session = _closed_session()
    before = _by_criterion(build_evidences(session))

    session_with_extras = _session_with_events(
        (EventType.CONVERSATION_AGENT_RESPONSE, Source.AGENT, {}),
        (EventType.CONVERSATION_USER_INPUT, Source.USER, {}),
        (EventType.CONVERSATION_GOAL_ACHIEVED, Source.SYSTEM, {}),
        (EventType.CONVERSATION_INTERRUPTION_DETECTED, Source.SYSTEM, {}),
        (EventType.CONVERSATION_SILENCE_DETECTED, Source.PLATFORM, {"count": 1}),
    )
    after = _by_criterion(build_evidences(session_with_extras))

    for criterion in ("total_turns", "agent_turns", "user_turns"):
        assert before[criterion].criterion == after[criterion].criterion
        assert before[criterion].dimension == after[criterion].dimension
        assert before[criterion].value == pytest.approx(after[criterion].value)
        assert len(before[criterion].source_events) == len(after[criterion].source_events)


def test_turn_started_and_ended_events_do_not_affect_turn_counts() -> None:
    session = _session_with_events(
        (EventType.CONVERSATION_AGENT_RESPONSE, Source.AGENT, {}),
        (EventType.CONVERSATION_USER_INPUT, Source.USER, {}),
        (EventType.CONVERSATION_TURN_STARTED, Source.SYSTEM, {}),
        (EventType.CONVERSATION_TURN_ENDED, Source.SYSTEM, {}),
    )

    evidences = _by_criterion(build_evidences(session))

    assert evidences["total_turns"].value == pytest.approx(2.0)
    assert evidences["agent_turns"].value == pytest.approx(1.0)
    assert evidences["user_turns"].value == pytest.approx(1.0)
    assert evidences["turn_completion_rate"].value == pytest.approx(1.0)


def test_conversational_evidences_no_regression_snapshot() -> None:
    """Locks criterion/dimension/evidence_type/value for the six conversational
    evidences on a fixed trace, ahead of the `_turns`/`_rate` dimension refactor."""
    session = _session_with_events(
        *[(EventType.CONVERSATION_AGENT_RESPONSE, Source.AGENT, {}) for _ in range(4)],
        *[(EventType.CONVERSATION_USER_INPUT, Source.USER, {}) for _ in range(4)],
        (EventType.CONVERSATION_GOAL_ACHIEVED, Source.SYSTEM, {}),
        (EventType.CONVERSATION_INTERRUPTION_DETECTED, Source.SYSTEM, {}),
        (EventType.CONVERSATION_SILENCE_DETECTED, Source.PLATFORM, {"count": 2}),
    )

    evidences = _by_criterion(build_evidences(session))

    expected = {
        "total_turns": (EvidenceType.INFERRED, Dimension.CONVERSATIONAL, 8.0),
        "agent_turns": (EvidenceType.INFERRED, Dimension.CONVERSATIONAL, 4.0),
        "user_turns": (EvidenceType.INFERRED, Dimension.CONVERSATIONAL, 4.0),
        "goal_completion": (EvidenceType.INFERRED, Dimension.CONVERSATIONAL, 1.0),
        "turn_completion_rate": (EvidenceType.INFERRED, Dimension.CONVERSATIONAL, 0.75),
        "prolonged_silence_rate": (EvidenceType.INFERRED, Dimension.CONVERSATIONAL, 0.25),
    }

    for criterion, (evidence_type, dimension, value) in expected.items():
        evidence = evidences[criterion]
        assert evidence.evidence_type is evidence_type
        assert evidence.dimension is dimension
        assert evidence.value == pytest.approx(value)


def test_model_invocation_count_evidence() -> None:
    session = _session_with_events(
        *[(EventType.SYSTEM_MODEL_INVOCATION, Source.SYSTEM, {}) for _ in range(3)],
    )
    invocation_events = [
        e for e in session.events if e.event_type is EventType.SYSTEM_MODEL_INVOCATION
    ]

    evidences = _by_criterion(build_evidences(session))

    invocations = evidences["model_invocation_count"]
    assert invocations.criterion == "model_invocation_count"
    assert invocations.dimension is Dimension.TECHNICAL
    assert invocations.evidence_type is EvidenceType.INFERRED
    assert invocations.value == pytest.approx(3.0)
    assert {e.event_id for e in invocation_events} == set(invocations.source_events)


def test_model_invocation_count_zero_without_events() -> None:
    session = _session_with_events()

    evidences = _by_criterion(build_evidences(session))

    invocations = evidences["model_invocation_count"]
    assert invocations.value == pytest.approx(0.0)
    assert invocations.source_events == []


def test_technical_error_rate_with_errors_and_turns() -> None:
    session = _session_with_events(
        (EventType.CONVERSATION_AGENT_RESPONSE, Source.AGENT, {}),
        (EventType.CONVERSATION_USER_INPUT, Source.USER, {}),
        (EventType.SYSTEM_ERROR, Source.SYSTEM, {}),
    )
    error_events = [e for e in session.events if e.event_type is EventType.SYSTEM_ERROR]

    evidences = _by_criterion(build_evidences(session))

    error_rate = evidences["technical_error_rate"]
    assert error_rate.criterion == "technical_error_rate"
    assert error_rate.dimension is Dimension.TECHNICAL
    assert error_rate.evidence_type is EvidenceType.INFERRED
    assert error_rate.value == pytest.approx(0.5)
    assert {e.event_id for e in error_events} == set(error_rate.source_events)


def test_technical_error_rate_zero_without_errors() -> None:
    session = _session_with_events(
        (EventType.CONVERSATION_AGENT_RESPONSE, Source.AGENT, {}),
        (EventType.CONVERSATION_USER_INPUT, Source.USER, {}),
    )

    evidences = _by_criterion(build_evidences(session))

    error_rate = evidences["technical_error_rate"]
    assert error_rate.value == pytest.approx(0.0)
    assert error_rate.source_events == []


def test_technical_error_rate_zero_denominator_guard() -> None:
    session = _session_with_events()

    evidences = _by_criterion(build_evidences(session))

    error_rate = evidences["technical_error_rate"]
    assert error_rate.value == pytest.approx(0.0)
    assert (
        error_rate.conclusion
        == "No agent or user turns were recorded, so technical error rate cannot be computed"
    )


def test_governance_flag_count_with_flags() -> None:
    session = _session_with_events(
        *[(EventType.SYSTEM_FLAG_RAISED, Source.SYSTEM, {}) for _ in range(2)],
    )
    flag_events = [e for e in session.events if e.event_type is EventType.SYSTEM_FLAG_RAISED]

    evidences = _by_criterion(build_evidences(session))

    flags = evidences["governance_flag_count"]
    assert flags.criterion == "governance_flag_count"
    assert flags.dimension is Dimension.RISK
    assert flags.evidence_type is EvidenceType.INFERRED
    assert flags.value == pytest.approx(2.0)
    assert {e.event_id for e in flag_events} == set(flags.source_events)


def test_governance_flag_count_zero_without_flags() -> None:
    session = _session_with_events()

    evidences = _by_criterion(build_evidences(session))

    flags = evidences["governance_flag_count"]
    assert flags.value == pytest.approx(0.0)
    assert flags.source_events == []


def test_unrecovered_error_present_with_error_and_failed_terminal() -> None:
    session = _session_with_error_and_terminal(failed=True)

    evidences = _by_criterion(build_evidences(session))

    unrecovered = evidences["unrecovered_error_present"]
    assert unrecovered.criterion == "unrecovered_error_present"
    assert unrecovered.dimension is Dimension.RISK
    assert unrecovered.evidence_type is EvidenceType.INFERRED
    assert unrecovered.value == pytest.approx(1.0)
    assert unrecovered.conclusion == "The session ended with an unrecovered error"

    error_events = [e for e in session.events if e.event_type is EventType.SYSTEM_ERROR]
    failed_events = [e for e in session.events if e.event_type is EventType.SESSION_FAILED]
    expected_source_events = {e.event_id for e in error_events} | {
        e.event_id for e in failed_events
    }
    assert set(unrecovered.source_events) == expected_source_events


def test_unrecovered_error_present_zero_with_clean_terminal() -> None:
    session = _session_with_error_and_terminal(failed=False)

    evidences = _by_criterion(build_evidences(session))

    unrecovered = evidences["unrecovered_error_present"]
    assert unrecovered.value == pytest.approx(0.0)
    assert unrecovered.conclusion == "The session had no unrecovered error"


def test_unrecovered_error_present_zero_without_error_events() -> None:
    session = _failed_session()

    evidences = _by_criterion(build_evidences(session))

    unrecovered = evidences["unrecovered_error_present"]
    assert unrecovered.value == pytest.approx(0.0)
    assert unrecovered.source_events == []


def _session_with_error_and_terminal(*, failed: bool) -> Session:
    session = Session.open("call-1", uuid4(), START)
    session.record(EventType.SESSION_STARTED, Source.PLATFORM, START, {})
    session.record(EventType.SYSTEM_ERROR, Source.SYSTEM, START, {})
    terminal_type = EventType.SESSION_FAILED if failed else EventType.SESSION_ENDED
    session.record(terminal_type, Source.PLATFORM, END, {})
    return session


def test_risk_evidences_do_not_affect_existing_conversational_and_technical_evidences() -> None:
    session = _session_with_events(
        *[(EventType.CONVERSATION_AGENT_RESPONSE, Source.AGENT, {}) for _ in range(4)],
        *[(EventType.CONVERSATION_USER_INPUT, Source.USER, {}) for _ in range(4)],
        (EventType.CONVERSATION_GOAL_ACHIEVED, Source.SYSTEM, {}),
        (EventType.CONVERSATION_INTERRUPTION_DETECTED, Source.SYSTEM, {}),
        (EventType.CONVERSATION_SILENCE_DETECTED, Source.PLATFORM, {"count": 2}),
        (EventType.SYSTEM_MODEL_INVOCATION, Source.SYSTEM, {}),
        (EventType.SYSTEM_ERROR, Source.SYSTEM, {}),
    )
    before = _by_criterion(build_evidences(session))

    session_with_risk = _session_with_events(
        *[(EventType.CONVERSATION_AGENT_RESPONSE, Source.AGENT, {}) for _ in range(4)],
        *[(EventType.CONVERSATION_USER_INPUT, Source.USER, {}) for _ in range(4)],
        (EventType.CONVERSATION_GOAL_ACHIEVED, Source.SYSTEM, {}),
        (EventType.CONVERSATION_INTERRUPTION_DETECTED, Source.SYSTEM, {}),
        (EventType.CONVERSATION_SILENCE_DETECTED, Source.PLATFORM, {"count": 2}),
        (EventType.SYSTEM_MODEL_INVOCATION, Source.SYSTEM, {}),
        (EventType.SYSTEM_ERROR, Source.SYSTEM, {}),
        (EventType.SYSTEM_FLAG_RAISED, Source.SYSTEM, {}),
    )
    after = _by_criterion(build_evidences(session_with_risk))

    for criterion in (
        "total_turns",
        "agent_turns",
        "user_turns",
        "goal_completion",
        "turn_completion_rate",
        "prolonged_silence_rate",
        "model_invocation_count",
        "technical_error_rate",
        "session_completed",
    ):
        assert before[criterion].dimension == after[criterion].dimension
        assert before[criterion].value == pytest.approx(after[criterion].value)

    assert "governance_flag_count" in after
    assert "unrecovered_error_present" in after


def test_risk_evidences_coexist_without_duplicate_criteria() -> None:
    session = _session_with_events(
        (EventType.CONVERSATION_AGENT_RESPONSE, Source.AGENT, {}),
        (EventType.CONVERSATION_USER_INPUT, Source.USER, {}),
        (EventType.SYSTEM_MODEL_INVOCATION, Source.SYSTEM, {}),
        (EventType.SYSTEM_ERROR, Source.SYSTEM, {}),
        (EventType.SYSTEM_FLAG_RAISED, Source.SYSTEM, {}),
    )

    evidences = build_evidences(session)
    criteria = [e.criterion for e in evidences]

    assert len(criteria) == len(set(criteria))
    dimensions = {e.dimension for e in evidences}
    assert Dimension.CONVERSATIONAL in dimensions
    assert Dimension.TECHNICAL in dimensions
    assert Dimension.RISK in dimensions


def test_technical_and_conversational_evidences_coexist_without_duplicates() -> None:
    session = _session_with_events(
        (EventType.CONVERSATION_AGENT_RESPONSE, Source.AGENT, {}),
        (EventType.CONVERSATION_USER_INPUT, Source.USER, {}),
        (EventType.SYSTEM_MODEL_INVOCATION, Source.SYSTEM, {}),
        (EventType.SYSTEM_ERROR, Source.SYSTEM, {}),
    )

    evidences = build_evidences(session)
    criteria = [e.criterion for e in evidences]

    assert len(criteria) == len(set(criteria))
    expected_criteria = {
        "total_turns",
        "agent_turns",
        "user_turns",
        "goal_completion",
        "turn_completion_rate",
        "prolonged_silence_rate",
        "session_duration_seconds",
        "session_completed",
        "model_invocation_count",
        "technical_error_rate",
    }
    assert expected_criteria.issubset(set(criteria))
