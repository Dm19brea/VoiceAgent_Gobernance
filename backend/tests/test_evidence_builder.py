from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

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
