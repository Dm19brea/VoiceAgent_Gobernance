"""M4.3 — Metric catalogue: build_metrics from a session's evidences (D2, R10)."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from src.domain.enums import Dimension, EventType, Source
from src.domain.evidence_builder import build_evidences
from src.domain.scoring.catalogue import build_metrics
from src.domain.scoring.metric import Metric
from src.domain.session import Session

START = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)


def _closed_session(
    *,
    agent_turns: int = 1,
    user_turns: int = 1,
    duration_seconds: int = 47,
    report: dict[str, Any] | None = None,
) -> Session:
    session = Session.open("call-1", uuid4(), START)
    session.record(EventType.SESSION_STARTED, Source.PLATFORM, START, {})
    for _ in range(agent_turns):
        session.record(EventType.CONVERSATION_AGENT_RESPONSE, Source.AGENT, START, {})
    for _ in range(user_turns):
        session.record(EventType.CONVERSATION_USER_INPUT, Source.USER, START, {})
    end = START + timedelta(seconds=duration_seconds)
    session.record(EventType.SESSION_ENDED, Source.PLATFORM, end, {"report": report or {}})
    return session


def _metrics(session: Session) -> dict[str, Metric]:
    return {m.code: m for m in build_metrics(session, build_evidences(session))}


def test_full_session_yields_the_four_catalogue_metrics() -> None:
    metrics = _metrics(_closed_session(report={"ended_reason": "customer-ended-call"}))

    assert set(metrics) == {"engagement", "completion", "duration", "clean_ending"}
    assert metrics["engagement"].dimension is Dimension.CONVERSATIONAL
    assert metrics["completion"].dimension is Dimension.TECHNICAL
    assert metrics["duration"].dimension is Dimension.TECHNICAL
    assert metrics["clean_ending"].dimension is Dimension.RISK


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


def test_clean_ending_is_full_for_a_normal_hangup() -> None:
    metrics = _metrics(_closed_session(report={"ended_reason": "customer-ended-call"}))

    assert metrics["clean_ending"].normalized_score == 100


def test_clean_ending_is_zero_for_a_bad_reason() -> None:
    metrics = _metrics(_closed_session(report={"ended_reason": "silence-timed-out"}))

    assert metrics["clean_ending"].normalized_score == 0


def test_clean_ending_is_zero_for_an_error_reason() -> None:
    metrics = _metrics(_closed_session(report={"ended_reason": "pipeline-error-openai-llm-failed"}))

    assert metrics["clean_ending"].normalized_score == 0


def test_metrics_without_source_evidence_are_omitted() -> None:
    # An active (never ended) session: only turn evidences exist -> only engagement.
    session = Session.open("call-2", uuid4(), START)
    session.record(EventType.SESSION_STARTED, Source.PLATFORM, START, {})

    metrics = {m.code for m in build_metrics(session, build_evidences(session))}

    assert metrics == {"engagement"}


def test_build_metrics_is_deterministic() -> None:
    session = _closed_session(report={"ended_reason": "assistant-ended-call"})
    evidences = build_evidences(session)

    first = build_metrics(session, evidences)
    second = build_metrics(session, evidences)

    assert first == second
