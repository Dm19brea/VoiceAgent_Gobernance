from datetime import UTC, datetime

import pytest
from pytest import LogCaptureFixture
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.use_cases.record_system_observation import RecordSystemObservation
from src.domain.agent import Agent
from src.domain.enums import EventType, SessionStatus, Source
from src.domain.session import Session
from src.infrastructure.celery import tasks as tasks_module
from src.infrastructure.celery.tasks import build_session_evidences_async
from src.infrastructure.repositories.governance_repository import SqlAlchemyGovernanceRepository

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
