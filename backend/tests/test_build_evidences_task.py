from datetime import UTC, datetime

import pytest
from pytest import LogCaptureFixture
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.ports.conversation_judge import JudgeVerdict
from src.application.use_cases.record_conversation_content import RecordConversationContent
from src.application.use_cases.record_conversation_signals import RecordConversationSignals
from src.application.use_cases.record_system_observation import RecordSystemObservation
from src.domain.agent import Agent
from src.domain.enums import Dimension, EventType, SessionStatus, Source
from src.domain.session import Session
from src.infrastructure.celery import tasks as tasks_module
from src.infrastructure.celery.tasks import build_session_evidences_async
from src.infrastructure.repositories.governance_repository import SqlAlchemyGovernanceRepository
from tests.fakes import FakeConversationJudge

START = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
END = datetime(2026, 1, 1, 10, 0, 30, tzinfo=UTC)


async def test_task_builds_and_persists_evidences(db_session: AsyncSession) -> None:
    repo = SqlAlchemyGovernanceRepository(db_session)
    agent = Agent(name="Citas", objective="Confirmar", vapi_assistant_id="asst-t8")
    await repo.add_agent(agent)

    session = Session.open("call-t8", agent.agent_id, START)
    report = {"report": {"ended_reason": "ok"}}
    session.record(EventType.SESSION_STARTED, Source.PLATFORM, START, {})
    session.record(EventType.CONVERSATION_USER_INPUT, Source.USER, START, {})
    session.record(EventType.SESSION_ENDED, Source.PLATFORM, END, report)
    await repo.save_session(session)
    await db_session.commit()

    count = await build_session_evidences_async("call-t8")

    assert count > 0
    evidences = await repo.get_evidences_by_session("call-t8")
    assert len(evidences) > 0
    assert any(e.criterion == "ended_reason" for e in evidences)


async def test_task_on_unknown_session_returns_zero(db_session: AsyncSession) -> None:
    count = await build_session_evidences_async("does-not-exist")

    assert count == 0


async def test_rebuilding_evidences_does_not_duplicate(db_session: AsyncSession) -> None:
    """Vapi can deliver the end-of-call webhook more than once, so the build task
    can run twice for the same session. Evidences must be replaced, not duplicated."""
    repo = SqlAlchemyGovernanceRepository(db_session)
    agent = Agent(name="Citas", objective="Confirmar", vapi_assistant_id="asst-dup")
    await repo.add_agent(agent)

    session = Session.open("call-dup", agent.agent_id, START)
    session.record(EventType.SESSION_STARTED, Source.PLATFORM, START, {})
    session.record(
        EventType.SESSION_ENDED, Source.PLATFORM, END, {"report": {"ended_reason": "ok"}}
    )
    await repo.save_session(session)
    await db_session.commit()

    first = await build_session_evidences_async("call-dup")
    await build_session_evidences_async("call-dup")

    evidences = await repo.get_evidences_by_session("call-dup")
    assert len(evidences) == first


async def test_task_persists_density_rates_idempotently(db_session: AsyncSession) -> None:
    repo = SqlAlchemyGovernanceRepository(db_session)
    agent = Agent(name="Citas", objective="Confirmar", vapi_assistant_id="asst-density-rates")
    await repo.add_agent(agent)

    session = Session.open("call-density-rates", agent.agent_id, START)
    session.record(EventType.CONVERSATION_AGENT_RESPONSE, Source.AGENT, START, {})
    session.record(EventType.CONVERSATION_USER_INPUT, Source.USER, START, {})
    session.record(EventType.TOOL_CALLED, Source.AGENT, START, {})
    session.record(EventType.TOOL_CALLED, Source.AGENT, START, {})
    session.record(EventType.SYSTEM_WARNING, Source.SYSTEM, START, {})
    session.record(
        EventType.SESSION_ENDED, Source.PLATFORM, END, {"report": {"ended_reason": "ok"}}
    )
    tool_event_ids = [
        event.event_id for event in session.events if event.event_type is EventType.TOOL_CALLED
    ]
    warning_event_ids = [
        event.event_id for event in session.events if event.event_type is EventType.SYSTEM_WARNING
    ]
    await repo.save_session(session)
    await db_session.commit()

    await build_session_evidences_async("call-density-rates")
    await build_session_evidences_async("call-density-rates")

    persisted = await repo.get_evidences_by_session("call-density-rates")
    density_rates = {
        criterion: [evidence for evidence in persisted if evidence.criterion == criterion]
        for criterion in ("tool_usage_density", "system_warning_rate")
    }
    assert all(len(rows) == 1 for rows in density_rates.values())

    tool_usage_density = density_rates["tool_usage_density"][0]
    assert tool_usage_density.dimension is Dimension.OPERATIONAL
    assert tool_usage_density.value == pytest.approx(2.0)
    assert tool_usage_density.source_events == tool_event_ids

    system_warning_rate = density_rates["system_warning_rate"][0]
    assert system_warning_rate.dimension is Dimension.RISK
    assert system_warning_rate.value == pytest.approx(0.5)
    assert system_warning_rate.source_events == warning_event_ids


async def test_task_builds_nonzero_density_rates_from_terminal_report_content(
    db_session: AsyncSession,
) -> None:
    repo = SqlAlchemyGovernanceRepository(db_session)
    agent = Agent(name="Citas", objective="Confirmar", vapi_assistant_id="asst-terminal-density")
    await repo.add_agent(agent)

    session = Session.open("call-terminal-density", agent.agent_id, START)
    session.record(EventType.TOOL_CALLED, Source.AGENT, START, {})
    session.record(EventType.SYSTEM_WARNING, Source.SYSTEM, START, {})
    session.record(
        EventType.SESSION_ENDED,
        Source.PLATFORM,
        END,
        _report_payload(
            [
                {"role": "user", "content": "Necesito una cita"},
                {"role": "assistant", "content": "Claro, ¿para qué día?"},
            ]
        ),
    )
    await repo.save_session(session)
    await db_session.commit()

    await build_session_evidences_async("call-terminal-density")

    first = await repo.get_evidences_by_session("call-terminal-density")
    first_rates = {
        evidence.criterion: evidence.value
        for evidence in first
        if evidence.criterion in {"tool_usage_density", "system_warning_rate"}
    }
    assert first_rates == {
        "tool_usage_density": pytest.approx(1.0),
        "system_warning_rate": pytest.approx(0.5),
    }

    await build_session_evidences_async("call-terminal-density")

    repeated = await repo.get_evidences_by_session("call-terminal-density")
    repeated_rates = {
        evidence.criterion: evidence.value
        for evidence in repeated
        if evidence.criterion in {"tool_usage_density", "system_warning_rate"}
    }
    assert repeated_rates == first_rates
    density_rows = [evidence for evidence in repeated if evidence.criterion == "tool_usage_density"]
    warning_rows = [
        evidence for evidence in repeated if evidence.criterion == "system_warning_rate"
    ]
    assert len(density_rows) == 1
    assert len(warning_rows) == 1


async def test_task_persists_turn_latency_aggregates_idempotently(
    db_session: AsyncSession,
) -> None:
    repo = SqlAlchemyGovernanceRepository(db_session)
    agent = Agent(name="Citas", objective="Confirmar", vapi_assistant_id="asst-latency")
    await repo.add_agent(agent)
    session = Session.open("call-latency", agent.agent_id, START)
    session.record(
        EventType.SESSION_ENDED,
        Source.PLATFORM,
        END,
        {"report": {"ended_reason": "ok", "turn_latencies_seconds": [0.5, 1.5]}},
    )
    terminal_event_id = session.events[-1].event_id
    await repo.save_session(session)
    await db_session.commit()

    await build_session_evidences_async("call-latency")
    await build_session_evidences_async("call-latency")

    evidences = await repo.get_evidences_by_session("call-latency")
    latency_evidences = {
        evidence.criterion: evidence
        for evidence in evidences
        if evidence.criterion in {"mean_turn_latency_seconds", "max_turn_latency_seconds"}
    }
    assert set(latency_evidences) == {
        "mean_turn_latency_seconds",
        "max_turn_latency_seconds",
    }
    assert latency_evidences["mean_turn_latency_seconds"].value == pytest.approx(1.0)
    assert latency_evidences["max_turn_latency_seconds"].value == pytest.approx(1.5)
    assert all(e.source_events == [terminal_event_id] for e in latency_evidences.values())


async def test_task_records_evaluation_triggered_marker_before_building_evidences(
    db_session: AsyncSession,
) -> None:
    repo = SqlAlchemyGovernanceRepository(db_session)
    agent = Agent(name="Citas", objective="Confirmar", vapi_assistant_id="asst-marker-task")
    await repo.add_agent(agent)

    session = Session.open("call-marker-task", agent.agent_id, START)
    session.record(EventType.SESSION_STARTED, Source.PLATFORM, START, {})
    session.record(
        EventType.SESSION_ENDED, Source.PLATFORM, END, {"report": {"ended_reason": "ok"}}
    )
    await repo.save_session(session)
    await db_session.commit()

    await build_session_evidences_async("call-marker-task")

    reloaded = await repo.get_session("call-marker-task")
    assert reloaded is not None
    marker_events = [
        e for e in reloaded.events if e.event_type is EventType.SESSION_EVALUATION_TRIGGERED
    ]
    assert len(marker_events) == 1
    assert marker_events[0].source is Source.PLATFORM
    assert marker_events[0].sequence_number == 3


async def test_task_retry_does_not_duplicate_evaluation_triggered_marker(
    db_session: AsyncSession,
) -> None:
    repo = SqlAlchemyGovernanceRepository(db_session)
    agent = Agent(name="Citas", objective="Confirmar", vapi_assistant_id="asst-marker-retry")
    await repo.add_agent(agent)

    session = Session.open("call-marker-retry", agent.agent_id, START)
    session.record(
        EventType.SESSION_ENDED, Source.PLATFORM, END, {"report": {"ended_reason": "ok"}}
    )
    await repo.save_session(session)
    await db_session.commit()

    await build_session_evidences_async("call-marker-retry")
    await build_session_evidences_async("call-marker-retry")

    reloaded = await repo.get_session("call-marker-retry")
    assert reloaded is not None
    marker_events = [
        e for e in reloaded.events if e.event_type is EventType.SESSION_EVALUATION_TRIGGERED
    ]
    assert len(marker_events) == 1


async def test_marker_survives_evidence_build_failure(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = SqlAlchemyGovernanceRepository(db_session)
    agent = Agent(name="Citas", objective="Confirmar", vapi_assistant_id="asst-marker-fail")
    await repo.add_agent(agent)

    session = Session.open("call-marker-fail", agent.agent_id, START)
    session.record(
        EventType.SESSION_ENDED, Source.PLATFORM, END, {"report": {"ended_reason": "ok"}}
    )
    await repo.save_session(session)
    await db_session.commit()

    def _boom(_session: Session) -> list[object]:
        raise RuntimeError("evidence building exploded")

    monkeypatch.setattr(tasks_module, "build_evidences", _boom)

    with pytest.raises(RuntimeError, match="evidence building exploded"):
        await build_session_evidences_async("call-marker-fail")

    reloaded = await repo.get_session("call-marker-fail")
    assert reloaded is not None
    marker_events = [
        e for e in reloaded.events if e.event_type is EventType.SESSION_EVALUATION_TRIGGERED
    ]
    assert len(marker_events) == 1


async def test_recoverable_evaluation_failure_records_one_error_without_lifecycle_mutation(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = SqlAlchemyGovernanceRepository(db_session)
    agent = Agent(name="Citas", objective="Confirmar", vapi_assistant_id="asst-evaluation-error")
    await repo.add_agent(agent)

    governance_session = Session.open("call-evaluation-error", agent.agent_id, START)
    governance_session.record(EventType.SESSION_STARTED, Source.PLATFORM, START, {})
    governance_session.record(EventType.SESSION_ENDED, Source.PLATFORM, END, {})
    await repo.save_session(governance_session)
    await db_session.commit()

    def _boom(_session: Session) -> list[object]:
        raise RuntimeError("evaluator dependency unavailable")

    monkeypatch.setattr(tasks_module, "build_evidences", _boom)

    for _ in range(2):
        with pytest.raises(RuntimeError, match="evaluator dependency unavailable"):
            await build_session_evidences_async("call-evaluation-error")

    reloaded = await repo.get_session("call-evaluation-error")
    assert reloaded is not None
    errors = [event for event in reloaded.events if event.event_type is EventType.SYSTEM_ERROR]
    assert len(errors) == 1
    assert errors[0].payload["classification"] == "recoverable_evaluation_failure"
    assert reloaded.status is SessionStatus.ENDED
    assert reloaded.ended_at == END


async def test_recoverable_evaluation_error_ignores_volatile_message_in_retry_identity(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = SqlAlchemyGovernanceRepository(db_session)
    agent = Agent(name="Citas", objective="Confirmar", vapi_assistant_id="asst-volatile-error")
    await repo.add_agent(agent)

    governance_session = Session.open("call-volatile-error", agent.agent_id, START)
    governance_session.record(EventType.SESSION_ENDED, Source.PLATFORM, END, {})
    await repo.save_session(governance_session)
    await db_session.commit()

    attempt = 0

    def _volatile_boom(_session: Session) -> list[object]:
        nonlocal attempt
        attempt += 1
        raise RuntimeError(f"evaluator unavailable request_id={attempt}")

    monkeypatch.setattr(tasks_module, "build_evidences", _volatile_boom)

    for _ in range(2):
        with pytest.raises(RuntimeError, match="evaluator unavailable request_id"):
            await build_session_evidences_async("call-volatile-error")

    reloaded = await repo.get_session("call-volatile-error")
    assert reloaded is not None
    errors = [event for event in reloaded.events if event.event_type is EventType.SYSTEM_ERROR]
    assert len(errors) == 1
    assert errors[0].payload["reason"] == "evaluator unavailable request_id=1"


async def test_evaluation_records_one_flag_per_accepted_finding_on_retry(
    db_session: AsyncSession,
) -> None:
    repo = SqlAlchemyGovernanceRepository(db_session)
    agent = Agent(name="Citas", objective="Confirmar", vapi_assistant_id="asst-evaluation-flag")
    await repo.add_agent(agent)

    governance_session = Session.open("call-evaluation-flag", agent.agent_id, START)
    governance_session.record(EventType.SESSION_STARTED, Source.PLATFORM, START, {})
    governance_session.record(EventType.SESSION_FAILED, Source.PLATFORM, END, {})
    await repo.save_session(governance_session)
    await db_session.commit()

    await build_session_evidences_async("call-evaluation-flag")
    await build_session_evidences_async("call-evaluation-flag")

    reloaded = await repo.get_session("call-evaluation-flag")
    assert reloaded is not None
    flags = [event for event in reloaded.events if event.event_type is EventType.SYSTEM_FLAG_RAISED]
    assert len(flags) == 1
    assert flags[0].payload["code"] == "session_failed"
    assert flags[0].payload["reason"] == "The session ended with an uncontrolled error."
    latencies = [
        event for event in reloaded.events if event.event_type is EventType.SYSTEM_LATENCY_MEASURED
    ]
    assert len(latencies) == 1
    assert latencies[0].payload["operation"] == "evidence_evaluation"
    assert latencies[0].payload["unit"] == "milliseconds"
    assert reloaded.status is SessionStatus.FAILED
    assert reloaded.ended_at == END


async def test_evaluation_error_observation_failure_does_not_recurse(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    caplog: LogCaptureFixture,
) -> None:
    repo = SqlAlchemyGovernanceRepository(db_session)
    agent = Agent(name="Citas", objective="Confirmar", vapi_assistant_id="asst-error-containment")
    await repo.add_agent(agent)
    governance_session = Session.open("call-error-containment", agent.agent_id, START)
    governance_session.record(EventType.SESSION_ENDED, Source.PLATFORM, END, {})
    await repo.save_session(governance_session)
    await db_session.commit()

    def _evaluation_boom(_session: Session) -> list[object]:
        raise RuntimeError("evaluation failed")

    async def _observation_boom(_self: RecordSystemObservation, _command: object) -> None:
        raise RuntimeError("observation persistence failed")

    monkeypatch.setattr(tasks_module, "build_evidences", _evaluation_boom)
    monkeypatch.setattr(RecordSystemObservation, "execute", _observation_boom)

    with pytest.raises(RuntimeError, match="evaluation failed"):
        await build_session_evidences_async("call-error-containment")

    assert caplog.text.count("Failed to record evaluation system observations") == 1
    reloaded = await repo.get_session("call-error-containment")
    assert reloaded is not None
    assert reloaded.status is SessionStatus.ENDED
    assert reloaded.ended_at == END


def _report_payload(messages_open_ai_formatted: list[dict[str, object]]) -> dict[str, object]:
    return {
        "report": {"ended_reason": "ok"},
        "artifact": {
            "messagesOpenAIFormatted": messages_open_ai_formatted,
            "messages": [],
        },
    }


def _timed_report_payload(
    *,
    formatted: list[dict[str, object]],
    raw: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "report": {"ended_reason": "ok"},
        "artifact": {
            "messagesOpenAIFormatted": formatted,
            "messages": raw,
        },
    }


async def _persist_timed_call(
    db_session: AsyncSession,
    *,
    session_id: str,
    assistant_id: str,
    formatted: list[dict[str, object]],
    raw: list[dict[str, object]],
) -> SqlAlchemyGovernanceRepository:
    repo = SqlAlchemyGovernanceRepository(db_session)
    agent = Agent(name="Citas", objective="Confirmar", vapi_assistant_id=assistant_id)
    await repo.add_agent(agent)
    session = Session.open(session_id, agent.agent_id, START)
    session.record(
        EventType.SESSION_ENDED,
        Source.PLATFORM,
        END,
        _timed_report_payload(formatted=formatted, raw=raw),
    )
    await repo.save_session(session)
    await db_session.commit()
    return repo


async def test_content_events_derived_after_evidence_and_evaluation_observations(
    db_session: AsyncSession,
) -> None:
    repo = SqlAlchemyGovernanceRepository(db_session)
    agent = Agent(name="Citas", objective="Confirmar", vapi_assistant_id="asst-content")
    await repo.add_agent(agent)

    session = Session.open("call-content-task", agent.agent_id, START)
    session.record(EventType.SESSION_STARTED, Source.PLATFORM, START, {})
    session.record(
        EventType.SESSION_ENDED,
        Source.PLATFORM,
        END,
        _report_payload(
            [
                {"role": "user", "content": "Hi"},
                {"role": "assistant", "content": "Hello!"},
            ]
        ),
    )
    await repo.save_session(session)
    await db_session.commit()

    await build_session_evidences_async("call-content-task")

    reloaded = await repo.get_session("call-content-task")
    assert reloaded is not None
    content_events = [
        e
        for e in reloaded.events
        if e.event_type
        in (EventType.CONVERSATION_USER_INPUT, EventType.CONVERSATION_AGENT_RESPONSE)
    ]
    assert [e.event_type for e in content_events] == [
        EventType.CONVERSATION_USER_INPUT,
        EventType.CONVERSATION_AGENT_RESPONSE,
    ]
    marker_index = next(
        i
        for i, e in enumerate(reloaded.events)
        if e.event_type is EventType.SESSION_EVALUATION_TRIGGERED
    )
    content_indexes = [i for i, e in enumerate(reloaded.events) if e in content_events]
    assert all(i > marker_index for i in content_indexes)
    assert content_events[1].sequence_number == content_events[0].sequence_number + 1


async def test_missing_messages_open_ai_formatted_produces_zero_content_events(
    db_session: AsyncSession,
) -> None:
    repo = SqlAlchemyGovernanceRepository(db_session)
    agent = Agent(name="Citas", objective="Confirmar", vapi_assistant_id="asst-content-empty")
    await repo.add_agent(agent)

    session = Session.open("call-content-empty", agent.agent_id, START)
    session.record(
        EventType.SESSION_ENDED, Source.PLATFORM, END, {"report": {"ended_reason": "ok"}}
    )
    await repo.save_session(session)
    await db_session.commit()

    count = await build_session_evidences_async("call-content-empty")

    assert count > 0
    reloaded = await repo.get_session("call-content-empty")
    assert reloaded is not None
    content_events = [
        e
        for e in reloaded.events
        if e.event_type
        in (EventType.CONVERSATION_USER_INPUT, EventType.CONVERSATION_AGENT_RESPONSE)
    ]
    assert content_events == []


async def test_reprocessing_report_does_not_duplicate_content_events(
    db_session: AsyncSession,
) -> None:
    repo = SqlAlchemyGovernanceRepository(db_session)
    agent = Agent(name="Citas", objective="Confirmar", vapi_assistant_id="asst-content-retry")
    await repo.add_agent(agent)

    session = Session.open("call-content-retry", agent.agent_id, START)
    session.record(
        EventType.SESSION_ENDED,
        Source.PLATFORM,
        END,
        _report_payload([{"role": "user", "content": "Hi"}]),
    )
    await repo.save_session(session)
    await db_session.commit()

    await build_session_evidences_async("call-content-retry")
    await build_session_evidences_async("call-content-retry")

    reloaded = await repo.get_session("call-content-retry")
    assert reloaded is not None
    content_events = [
        e for e in reloaded.events if e.event_type is EventType.CONVERSATION_USER_INPUT
    ]
    assert len(content_events) == 1


async def test_conversation_content_failure_does_not_raise_or_rollback_evaluation(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    caplog: LogCaptureFixture,
) -> None:
    repo = SqlAlchemyGovernanceRepository(db_session)
    agent = Agent(name="Citas", objective="Confirmar", vapi_assistant_id="asst-content-fail")
    await repo.add_agent(agent)

    session = Session.open("call-content-fail", agent.agent_id, START)
    session.record(
        EventType.SESSION_ENDED,
        Source.PLATFORM,
        END,
        _report_payload([{"role": "user", "content": "Hi"}]),
    )
    await repo.save_session(session)
    await db_session.commit()

    async def _boom(_self: RecordConversationContent, _session_id: str, _commands: object) -> None:
        raise RuntimeError("conversation content persistence failed")

    monkeypatch.setattr(RecordConversationContent, "execute", _boom)

    count = await build_session_evidences_async("call-content-fail")

    assert count > 0
    assert caplog.text.count("Failed to record conversation content") == 1
    reloaded = await repo.get_session("call-content-fail")
    assert reloaded is not None
    assert reloaded.status is SessionStatus.ENDED
    assert reloaded.ended_at == END


def _achieved_verdict(*, count: int = 3, topics: list[str] | None = None) -> JudgeVerdict:
    return JudgeVerdict(
        topic_change_count=count,
        topics=topics if topics is not None else ["billing", "cancellation", "retention"],
        topic_reason="shifted three times",
        goal_achieved=True,
        goal_reason="issue resolved",
    )


def _info_only_verdict() -> JudgeVerdict:
    return JudgeVerdict(
        topic_change_count=0,
        topics=[],
        topic_reason=None,
        goal_achieved=True,
        goal_reason="information-only call",
    )


def _failed_verdict() -> JudgeVerdict:
    return JudgeVerdict(
        topic_change_count=0,
        topics=[],
        topic_reason=None,
        goal_achieved=False,
        goal_reason="appointment was not confirmed",
    )


async def test_conversation_signals_run_after_conversation_content(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = SqlAlchemyGovernanceRepository(db_session)
    agent = Agent(name="Citas", objective="Confirmar", vapi_assistant_id="asst-signal-order")
    await repo.add_agent(agent)

    session = Session.open("call-signal-order", agent.agent_id, START)
    session.record(
        EventType.SESSION_ENDED,
        Source.PLATFORM,
        END,
        _report_payload([{"role": "user", "content": "Hi"}]),
    )
    await repo.save_session(session)
    await db_session.commit()

    fake_judge = FakeConversationJudge(_achieved_verdict())
    monkeypatch.setattr(tasks_module, "OpenRouterConversationJudge", lambda: fake_judge)

    await build_session_evidences_async("call-signal-order")

    reloaded = await repo.get_session("call-signal-order")
    assert reloaded is not None
    content_index = next(
        i
        for i, e in enumerate(reloaded.events)
        if e.event_type is EventType.CONVERSATION_USER_INPUT
    )
    signal_indexes = [
        i
        for i, e in enumerate(reloaded.events)
        if e.event_type
        in (
            EventType.CONVERSATION_TOPIC_CHANGE,
            EventType.CONVERSATION_GOAL_ACHIEVED,
            EventType.CONVERSATION_GOAL_FAILED,
        )
    ]
    assert signal_indexes
    assert all(i > content_index for i in signal_indexes)
    assert len(fake_judge.calls) == 1


async def test_silence_pipeline_aggregates_intervals_once_with_chronological_timestamp(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = await _persist_timed_call(
        db_session,
        session_id="call-silence",
        assistant_id="asst-silence",
        formatted=[
            {"role": "assistant", "content": "First question?"},
            {"role": "user", "content": "First answer."},
            {"role": "assistant", "content": "Second question?"},
            {"role": "user", "content": "Second answer."},
        ],
        raw=[
            {"role": "bot", "time": 1000, "endTime": 2000},
            {"role": "user", "time": 8000, "endTime": 9000},
            {"role": "bot", "time": 10000, "endTime": 11000},
            {"role": "user", "time": 19000, "endTime": 20000},
        ],
    )
    monkeypatch.setattr(
        tasks_module,
        "OpenRouterConversationJudge",
        lambda: FakeConversationJudge(_info_only_verdict()),
    )

    await build_session_evidences_async("call-silence")
    await build_session_evidences_async("call-silence")

    reloaded = await repo.get_session("call-silence")
    assert reloaded is not None
    silence_events = [
        event
        for event in reloaded.events
        if event.event_type is EventType.CONVERSATION_SILENCE_DETECTED
    ]
    assert len(silence_events) == 1
    silence = silence_events[0]
    assert silence.payload["count"] == 2
    assert len(silence.payload["intervals"]) == 2
    assert silence.payload["threshold_ms"] == 6000
    assert silence.payload["detector_version"] == "assistant-user-interior-gap/v1"
    assert silence.timestamp == datetime.fromtimestamp(19, tz=UTC)
    assert silence.timestamp < END
    assert silence.sequence_number > next(
        event.sequence_number
        for event in reloaded.events
        if event.event_type is EventType.SESSION_ENDED
    )
    assert silence.sequence_number < next(
        event.sequence_number
        for event in reloaded.events
        if event.event_type is EventType.CONVERSATION_GOAL_ACHIEVED
    )


async def test_silence_pipeline_emits_nothing_without_qualifying_gap(
    db_session: AsyncSession,
) -> None:
    repo = await _persist_timed_call(
        db_session,
        session_id="call-no-silence",
        assistant_id="asst-no-silence",
        formatted=[
            {"role": "assistant", "content": "Question?"},
            {"role": "user", "content": "Answer."},
        ],
        raw=[
            {"role": "bot", "time": 1000, "endTime": 2000},
            {"role": "user", "time": 7999, "endTime": 9000},
        ],
    )

    await build_session_evidences_async("call-no-silence")

    reloaded = await repo.get_session("call-no-silence")
    assert reloaded is not None
    assert all(
        event.event_type is not EventType.CONVERSATION_SILENCE_DETECTED for event in reloaded.events
    )


async def test_malformed_silence_timing_isolated_while_judge_completes(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = await _persist_timed_call(
        db_session,
        session_id="call-silence-malformed",
        assistant_id="asst-malformed",
        formatted=[
            {"role": "assistant", "content": "Question?"},
            {"role": "user", "content": "Answer."},
        ],
        raw=[
            {"role": "bot", "time": "not-a-timestamp", "endTime": None},
            {"role": "user", "time": 8000, "endTime": 9000},
        ],
    )
    monkeypatch.setattr(
        tasks_module,
        "OpenRouterConversationJudge",
        lambda: FakeConversationJudge(_info_only_verdict()),
    )

    await build_session_evidences_async("call-silence-malformed")

    reloaded = await repo.get_session("call-silence-malformed")
    assert reloaded is not None
    assert all(
        event.event_type is not EventType.CONVERSATION_SILENCE_DETECTED for event in reloaded.events
    )
    assert any(
        event.event_type is EventType.CONVERSATION_GOAL_ACHIEVED for event in reloaded.events
    )


async def test_silence_failure_isolated_from_content_scoring_and_judge(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    caplog: LogCaptureFixture,
) -> None:
    repo = await _persist_timed_call(
        db_session,
        session_id="call-silence-fail",
        assistant_id="asst-silence-fail",
        formatted=[
            {"role": "assistant", "content": "Question?"},
            {"role": "user", "content": "Answer."},
        ],
        raw=[
            {"role": "bot", "time": 1000, "endTime": 2000},
            {"role": "user", "time": 8000, "endTime": 9000},
        ],
    )

    def _boom(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("silence detector failed")

    monkeypatch.setattr(tasks_module, "detect_user_response_silence", _boom)
    monkeypatch.setattr(
        tasks_module,
        "OpenRouterConversationJudge",
        lambda: FakeConversationJudge(_info_only_verdict()),
    )

    count = await build_session_evidences_async("call-silence-fail")

    assert count > 0
    assert caplog.text.count("Failed to record conversation silence") == 1
    reloaded = await repo.get_session("call-silence-fail")
    assert reloaded is not None
    assert any(
        event.event_type is EventType.CONVERSATION_AGENT_RESPONSE for event in reloaded.events
    )
    assert any(
        event.event_type is EventType.CONVERSATION_GOAL_ACHIEVED for event in reloaded.events
    )
    assert all(
        event.event_type is not EventType.CONVERSATION_SILENCE_DETECTED for event in reloaded.events
    )


async def test_conversation_signals_success_path_writes_topic_and_goal_events(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = SqlAlchemyGovernanceRepository(db_session)
    agent = Agent(name="Citas", objective="Confirmar", vapi_assistant_id="asst-signal-success")
    await repo.add_agent(agent)

    session = Session.open("call-signal-success", agent.agent_id, START)
    session.record(
        EventType.SESSION_ENDED,
        Source.PLATFORM,
        END,
        _report_payload([{"role": "user", "content": "Hi"}]),
    )
    await repo.save_session(session)
    await db_session.commit()

    monkeypatch.setattr(
        tasks_module,
        "OpenRouterConversationJudge",
        lambda: FakeConversationJudge(_achieved_verdict()),
    )

    await build_session_evidences_async("call-signal-success")
    await build_session_evidences_async("call-signal-success")  # reprocessing

    reloaded = await repo.get_session("call-signal-success")
    assert reloaded is not None
    topic_events = [
        e for e in reloaded.events if e.event_type is EventType.CONVERSATION_TOPIC_CHANGE
    ]
    goal_achieved_events = [
        e for e in reloaded.events if e.event_type is EventType.CONVERSATION_GOAL_ACHIEVED
    ]
    goal_failed_events = [
        e for e in reloaded.events if e.event_type is EventType.CONVERSATION_GOAL_FAILED
    ]
    assert len(topic_events) == 1
    assert len(goal_achieved_events) == 1
    assert len(goal_failed_events) == 0


async def test_conversation_signals_goal_failed_path_writes_only_goal_failed(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = SqlAlchemyGovernanceRepository(db_session)
    agent = Agent(name="Citas", objective="Confirmar", vapi_assistant_id="asst-signal-failed")
    await repo.add_agent(agent)

    session = Session.open("call-signal-failed", agent.agent_id, START)
    session.record(
        EventType.SESSION_ENDED,
        Source.PLATFORM,
        END,
        _report_payload([{"role": "user", "content": "I could not confirm the appointment."}]),
    )
    await repo.save_session(session)
    await db_session.commit()

    monkeypatch.setattr(
        tasks_module,
        "OpenRouterConversationJudge",
        lambda: FakeConversationJudge(_failed_verdict()),
    )

    await build_session_evidences_async("call-signal-failed")

    reloaded = await repo.get_session("call-signal-failed")
    assert reloaded is not None
    goal_achieved_events = [
        e for e in reloaded.events if e.event_type is EventType.CONVERSATION_GOAL_ACHIEVED
    ]
    goal_failed_events = [
        e for e in reloaded.events if e.event_type is EventType.CONVERSATION_GOAL_FAILED
    ]
    assert goal_achieved_events == []
    assert len(goal_failed_events) == 1
    assert goal_failed_events[0].payload["reason"] == "appointment was not confirmed"
    assert goal_failed_events[0].payload["identity"] == str(goal_failed_events[0].event_id)


async def test_conversation_signals_info_only_call_yields_only_goal_achieved(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = SqlAlchemyGovernanceRepository(db_session)
    agent = Agent(name="Citas", objective="Confirmar", vapi_assistant_id="asst-signal-info")
    await repo.add_agent(agent)

    session = Session.open("call-signal-info", agent.agent_id, START)
    session.record(
        EventType.SESSION_ENDED,
        Source.PLATFORM,
        END,
        _report_payload([{"role": "user", "content": "What are your hours?"}]),
    )
    await repo.save_session(session)
    await db_session.commit()

    monkeypatch.setattr(
        tasks_module,
        "OpenRouterConversationJudge",
        lambda: FakeConversationJudge(_info_only_verdict()),
    )

    await build_session_evidences_async("call-signal-info")

    reloaded = await repo.get_session("call-signal-info")
    assert reloaded is not None
    topic_events = [
        e for e in reloaded.events if e.event_type is EventType.CONVERSATION_TOPIC_CHANGE
    ]
    goal_achieved_events = [
        e for e in reloaded.events if e.event_type is EventType.CONVERSATION_GOAL_ACHIEVED
    ]
    assert topic_events == []
    assert len(goal_achieved_events) == 1


async def test_conversation_signals_retry_exhaustion_yields_zero_signals_content_intact(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = SqlAlchemyGovernanceRepository(db_session)
    agent = Agent(name="Citas", objective="Confirmar", vapi_assistant_id="asst-signal-exhaust")
    await repo.add_agent(agent)

    session = Session.open("call-signal-exhaust", agent.agent_id, START)
    session.record(
        EventType.SESSION_ENDED,
        Source.PLATFORM,
        END,
        _report_payload([{"role": "user", "content": "Hi"}]),
    )
    await repo.save_session(session)
    await db_session.commit()

    monkeypatch.setattr(
        tasks_module, "OpenRouterConversationJudge", lambda: FakeConversationJudge(None)
    )

    await build_session_evidences_async("call-signal-exhaust")

    reloaded = await repo.get_session("call-signal-exhaust")
    assert reloaded is not None
    signal_events = [
        e
        for e in reloaded.events
        if e.event_type
        in (
            EventType.CONVERSATION_TOPIC_CHANGE,
            EventType.CONVERSATION_GOAL_ACHIEVED,
            EventType.CONVERSATION_GOAL_FAILED,
        )
    ]
    content_events = [
        e for e in reloaded.events if e.event_type is EventType.CONVERSATION_USER_INPUT
    ]
    assert signal_events == []
    assert len(content_events) == 1


async def test_conversation_signals_failure_does_not_raise_or_affect_content(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    caplog: LogCaptureFixture,
) -> None:
    repo = SqlAlchemyGovernanceRepository(db_session)
    agent = Agent(name="Citas", objective="Confirmar", vapi_assistant_id="asst-signal-boom")
    await repo.add_agent(agent)

    session = Session.open("call-signal-boom", agent.agent_id, START)
    session.record(
        EventType.SESSION_ENDED,
        Source.PLATFORM,
        END,
        _report_payload([{"role": "user", "content": "Hi"}]),
    )
    await repo.save_session(session)
    await db_session.commit()

    async def _boom(_self: RecordConversationSignals, _session_id: str, _commands: object) -> None:
        raise RuntimeError("conversation signal persistence failed")

    monkeypatch.setattr(
        tasks_module,
        "OpenRouterConversationJudge",
        lambda: FakeConversationJudge(_achieved_verdict()),
    )
    monkeypatch.setattr(RecordConversationSignals, "execute", _boom)

    count = await build_session_evidences_async("call-signal-boom")

    assert count > 0
    assert caplog.text.count("Failed to record conversation signals") == 1
    reloaded = await repo.get_session("call-signal-boom")
    assert reloaded is not None
    assert reloaded.status is SessionStatus.ENDED
    assert reloaded.ended_at == END
    content_events = [
        e for e in reloaded.events if e.event_type is EventType.CONVERSATION_USER_INPUT
    ]
    assert len(content_events) == 1
