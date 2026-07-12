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
