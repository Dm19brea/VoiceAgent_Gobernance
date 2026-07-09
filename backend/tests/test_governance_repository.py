import asyncio
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy import Table, UniqueConstraint, insert, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

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


async def test_unique_session_sequence_prevents_competing_canonical_appends(
    db_session: AsyncSession,
) -> None:
    repo = SqlAlchemyGovernanceRepository(db_session)
    event_table = cast(Table, EventModel.__table__)
    assert any(
        isinstance(constraint, UniqueConstraint) and constraint.name == "uq_events_session_sequence"
        for constraint in event_table.constraints
    )
    constraint_exists = await db_session.scalar(
        text("SELECT to_regclass('uq_events_session_sequence') IS NOT NULL")
    )
    if not constraint_exists:
        await db_session.execute(
            text(
                "ALTER TABLE events ADD CONSTRAINT uq_events_session_sequence "
                "UNIQUE (session_id, sequence_number)"
            )
        )
        await db_session.commit()
    agent = Agent(name="Citas", objective="Confirmar", vapi_assistant_id="asst-sequence")
    await repo.add_agent(agent)
    session = Session.open("call-sequence", agent.agent_id, datetime.now(UTC))
    session.record(EventType.SESSION_ENDED, Source.PLATFORM, datetime.now(UTC), {})
    await repo.save_session(session)
    await db_session.commit()

    first = Event(
        event_id=uuid4(),
        session_id=session.session_id,
        event_type=EventType.SYSTEM_ERROR,
        source=Source.SYSTEM,
        sequence_number=2,
        timestamp=datetime.now(UTC),
        payload={"identity": "first"},
    )
    second = Event(
        event_id=uuid4(),
        session_id=session.session_id,
        event_type=EventType.SYSTEM_FLAG_RAISED,
        source=Source.SYSTEM,
        sequence_number=2,
        timestamp=datetime.now(UTC),
        payload={"identity": "second"},
    )
    assert await repo.append_event(first) is True
    await db_session.commit()

    with pytest.raises(IntegrityError):
        await repo.append_event(second)
        await db_session.commit()
    await db_session.rollback()


async def test_append_event_is_idempotent_for_a_duplicate_canonical_identity(
    db_session: AsyncSession,
) -> None:
    repo = SqlAlchemyGovernanceRepository(db_session)
    agent = Agent(name="Citas", objective="Confirmar", vapi_assistant_id="asst-event-identity")
    await repo.add_agent(agent)
    session = Session.open("call-event-identity", agent.agent_id, datetime.now(UTC))
    session.record(EventType.SESSION_ENDED, Source.PLATFORM, datetime.now(UTC), {})
    await repo.save_session(session)
    await db_session.commit()

    observation = Event(
        event_id=uuid4(),
        session_id=session.session_id,
        event_type=EventType.SYSTEM_ERROR,
        source=Source.SYSTEM,
        sequence_number=2,
        timestamp=datetime.now(UTC),
        payload={"identity": "stable-observation"},
    )

    assert await repo.append_event(observation) is True
    assert await repo.append_event(observation) is False
    await db_session.commit()

    reloaded = await repo.get_session(session.session_id)
    assert reloaded is not None
    assert [event.event_id for event in reloaded.events].count(observation.event_id) == 1
    assert reloaded.status is SessionStatus.ENDED


async def test_session_lock_serializes_system_and_marker_sequence_assignment(
    db_session: AsyncSession,
) -> None:
    """A second canonical append waits for the session lock and gets the next sequence."""
    repo = SqlAlchemyGovernanceRepository(db_session)
    agent = Agent(name="Citas", objective="Confirmar", vapi_assistant_id="asst-lock")
    await repo.add_agent(agent)
    session = Session.open("call-lock", agent.agent_id, datetime.now(UTC))
    session.record(EventType.SESSION_ENDED, Source.PLATFORM, datetime.now(UTC), {})
    await repo.save_session(session)
    await db_session.commit()

    engine = db_session.bind
    assert isinstance(engine, AsyncEngine)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as first_db:
        first_repo = SqlAlchemyGovernanceRepository(first_db)
        locked = await first_repo.get_session_for_update(session.session_id)
        assert locked is not None
        observation = locked.append_system_observation(
            EventType.SYSTEM_ERROR,
            Source.SYSTEM,
            datetime.now(UTC),
            {"identity": "serialized-error"},
            event_id=uuid4(),
        )
        assert await first_repo.append_event(observation) is True

        async def append_marker_after_lock() -> None:
            async with maker() as second_db:
                second_repo = SqlAlchemyGovernanceRepository(second_db)
                reloaded = await second_repo.get_session_for_update(session.session_id)
                assert reloaded is not None
                marker = reloaded.append_marker(
                    EventType.SESSION_EVALUATION_TRIGGERED,
                    Source.PLATFORM,
                    datetime.now(UTC),
                    {},
                )
                await second_repo.append_marker_event(marker)
                await second_db.commit()

        append_task = asyncio.create_task(append_marker_after_lock())
        await asyncio.sleep(0.05)
        assert not append_task.done()
        await first_db.commit()
        await append_task

    reloaded = await repo.get_session(session.session_id)
    assert reloaded is not None
    assert [event.sequence_number for event in reloaded.events] == [1, 2, 3]
