from datetime import UTC, datetime

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.agent import Agent
from src.domain.enums import EventType, SessionStatus, Source
from src.domain.event import Event
from src.domain.session import Session
from src.infrastructure.db.models import EventModel
from src.infrastructure.repositories.governance_repository import SqlAlchemyGovernanceRepository


async def test_partial_unique_index_rejects_duplicate_marker_rows(
    db_session: AsyncSession,
) -> None:
    """The partial unique index on (session_id, event_type) for marker events
    must exist in the test schema (mirrored on the ORM model), not only in the
    Alembic migration, since tests build the schema via ``create_all``."""
    agent = Agent(name="Citas", objective="Confirmar", vapi_assistant_id="asst-idx")
    repo = SqlAlchemyGovernanceRepository(db_session)
    await repo.add_agent(agent)

    session = Session.open("call-idx", agent.agent_id, datetime.now(UTC))
    session.record(EventType.SESSION_ENDED, Source.PLATFORM, datetime.now(UTC), {})
    await repo.save_session(session)
    await db_session.commit()

    marker_event = Event(
        session_id="call-idx",
        event_type=EventType.SESSION_EVALUATION_TRIGGERED,
        source=Source.PLATFORM,
        sequence_number=2,
        timestamp=datetime.now(UTC),
        payload={},
    )
    await db_session.execute(
        insert(EventModel).values(
            event_id=marker_event.event_id,
            session_id=marker_event.session_id,
            event_type=marker_event.event_type.value,
            source=marker_event.source.value,
            sequence_number=marker_event.sequence_number,
            timestamp=marker_event.timestamp,
            payload=marker_event.payload,
        )
    )
    await db_session.commit()

    duplicate_event = Event(
        session_id="call-idx",
        event_type=EventType.SESSION_EVALUATION_TRIGGERED,
        source=Source.PLATFORM,
        sequence_number=3,
        timestamp=datetime.now(UTC),
        payload={},
    )
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    stmt = (
        pg_insert(EventModel)
        .values(
            event_id=duplicate_event.event_id,
            session_id=duplicate_event.session_id,
            event_type=duplicate_event.event_type.value,
            source=duplicate_event.source.value,
            sequence_number=duplicate_event.sequence_number,
            timestamp=duplicate_event.timestamp,
            payload=duplicate_event.payload,
        )
        .on_conflict_do_nothing(
            index_elements=["session_id", "event_type"],
            index_where=EventModel.event_type.in_(
                [EventType.SESSION_EVALUATION_TRIGGERED.value, EventType.SESSION_FAILED.value]
            ),
        )
    )
    await db_session.execute(stmt)
    await db_session.commit()

    reloaded = await repo.get_session("call-idx")
    assert reloaded is not None
    marker_events = [
        e for e in reloaded.events if e.event_type is EventType.SESSION_EVALUATION_TRIGGERED
    ]
    assert len(marker_events) == 1


async def test_append_marker_event_persists_a_single_row(db_session: AsyncSession) -> None:
    repo = SqlAlchemyGovernanceRepository(db_session)
    agent = Agent(name="Citas", objective="Confirmar", vapi_assistant_id="asst-marker")
    await repo.add_agent(agent)

    session = Session.open("call-marker", agent.agent_id, datetime.now(UTC))
    session.record(EventType.SESSION_ENDED, Source.PLATFORM, datetime.now(UTC), {})
    await repo.save_session(session)
    await db_session.commit()

    marker_event = session.append_marker(
        EventType.SESSION_EVALUATION_TRIGGERED, Source.PLATFORM, datetime.now(UTC), {}
    )
    await repo.append_marker_event(marker_event)
    await db_session.commit()

    reloaded = await repo.get_session("call-marker")
    assert reloaded is not None
    marker_events = [
        e for e in reloaded.events if e.event_type is EventType.SESSION_EVALUATION_TRIGGERED
    ]
    assert len(marker_events) == 1
    assert marker_events[0].sequence_number == marker_event.sequence_number
    # The repo method never rewrites the closed session row.
    assert reloaded.status is SessionStatus.ENDED
    assert reloaded.ended_at == session.ended_at


async def test_append_marker_event_is_idempotent_on_conflict(db_session: AsyncSession) -> None:
    repo = SqlAlchemyGovernanceRepository(db_session)
    agent = Agent(name="Citas", objective="Confirmar", vapi_assistant_id="asst-marker-dup")
    await repo.add_agent(agent)

    session = Session.open("call-marker-dup", agent.agent_id, datetime.now(UTC))
    session.record(EventType.SESSION_ENDED, Source.PLATFORM, datetime.now(UTC), {})
    await repo.save_session(session)
    await db_session.commit()

    first_marker = session.append_marker(
        EventType.SESSION_EVALUATION_TRIGGERED, Source.PLATFORM, datetime.now(UTC), {}
    )
    await repo.append_marker_event(first_marker)
    await db_session.commit()

    # Simulate a retry: a second, distinct event_id for the same (session_id, event_type).
    second_marker = Event(
        session_id="call-marker-dup",
        event_type=EventType.SESSION_EVALUATION_TRIGGERED,
        source=Source.PLATFORM,
        sequence_number=first_marker.sequence_number,
        timestamp=datetime.now(UTC),
        payload={},
    )
    await repo.append_marker_event(second_marker)
    await db_session.commit()

    reloaded = await repo.get_session("call-marker-dup")
    assert reloaded is not None
    marker_events = [
        e for e in reloaded.events if e.event_type is EventType.SESSION_EVALUATION_TRIGGERED
    ]
    assert len(marker_events) == 1


async def test_repository_persists_and_reloads_session(db_session: AsyncSession) -> None:
    repo = SqlAlchemyGovernanceRepository(db_session)

    agent = Agent(name="Citas", objective="Confirmar", vapi_assistant_id="asst-x")
    await repo.add_agent(agent)

    session = Session.open("call-x", agent.agent_id, datetime.now(UTC))
    session.record(EventType.SESSION_STARTED, Source.PLATFORM, datetime.now(UTC), {})
    await repo.save_session(session)
    await db_session.commit()

    reloaded = await repo.get_session("call-x")
    assert reloaded is not None
    assert len(reloaded.events) == 1
    assert reloaded.events[0].event_type is EventType.SESSION_STARTED

    resolved = await repo.get_agent_by_assistant_id("asst-x")
    assert resolved is not None
    assert resolved.agent_id == agent.agent_id
