from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.agent import Agent
from src.domain.enums import EventType, Source
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
