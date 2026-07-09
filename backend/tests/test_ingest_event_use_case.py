from datetime import UTC, datetime
from uuid import uuid4

from src.application.commands import IngestEventCommand
from src.application.use_cases.ingest_event import IngestEvent
from src.domain.enums import AgentStatus, EventType, SessionStatus, Source
from src.domain.session import Session
from tests.fakes import InMemoryGovernanceRepository


def _cmd(
    event_type: EventType,
    source: Source = Source.PLATFORM,
    call_id: str = "call-1",
    assistant_id: str = "asst-1",
) -> IngestEventCommand:
    return IngestEventCommand(
        call_id=call_id,
        assistant_id=assistant_id,
        event_type=event_type,
        source=source,
        timestamp=datetime.now(UTC),
        payload={},
    )


async def test_new_call_creates_session_and_records_started() -> None:
    repo = InMemoryGovernanceRepository()

    await IngestEvent(repo).execute(_cmd(EventType.SESSION_STARTED))

    session = await repo.get_session("call-1")
    assert session is not None
    assert session.status is SessionStatus.ACTIVE
    assert len(session.events) == 1
    assert session.events[0].event_type is EventType.SESSION_STARTED
    assert session.events[0].sequence_number == 1


async def test_unknown_assistant_is_auto_provisioned() -> None:
    repo = InMemoryGovernanceRepository()

    await IngestEvent(repo).execute(_cmd(EventType.SESSION_STARTED, assistant_id="unknown"))

    agent = await repo.get_agent_by_assistant_id("unknown")
    assert agent is not None
    assert agent.status is AgentStatus.UNREGISTERED


async def test_second_event_appends_with_next_sequence() -> None:
    repo = InMemoryGovernanceRepository()
    use_case = IngestEvent(repo)

    await use_case.execute(_cmd(EventType.SESSION_STARTED))
    await use_case.execute(_cmd(EventType.CONVERSATION_USER_INPUT, source=Source.USER))

    session = await repo.get_session("call-1")
    assert session is not None
    assert len(session.events) == 2
    assert session.events[1].sequence_number == 2


async def test_end_of_call_closes_session() -> None:
    repo = InMemoryGovernanceRepository()
    use_case = IngestEvent(repo)

    await use_case.execute(_cmd(EventType.SESSION_STARTED))
    await use_case.execute(_cmd(EventType.SESSION_ENDED))

    session = await repo.get_session("call-1")
    assert session is not None
    assert session.status is SessionStatus.ENDED
    assert session.ended_at is not None


async def test_failed_call_fails_session() -> None:
    repo = InMemoryGovernanceRepository()
    use_case = IngestEvent(repo)

    await use_case.execute(_cmd(EventType.SESSION_STARTED))
    await use_case.execute(_cmd(EventType.SESSION_FAILED))

    session = await repo.get_session("call-1")
    assert session is not None
    assert session.status is SessionStatus.FAILED
    assert session.ended_at is not None
    assert len(session.events) == 2
    assert session.events[1].event_type is EventType.SESSION_FAILED


async def test_events_after_close_are_ignored() -> None:
    repo = InMemoryGovernanceRepository()
    use_case = IngestEvent(repo)

    await use_case.execute(_cmd(EventType.SESSION_STARTED))
    await use_case.execute(_cmd(EventType.SESSION_ENDED))
    await use_case.execute(_cmd(EventType.CONVERSATION_USER_INPUT, source=Source.USER))

    session = await repo.get_session("call-1")
    assert session is not None
    assert session.status is SessionStatus.ENDED
    assert len(session.events) == 2


async def test_events_after_failed_are_ignored() -> None:
    repo = InMemoryGovernanceRepository()
    use_case = IngestEvent(repo)

    await use_case.execute(_cmd(EventType.SESSION_STARTED))
    await use_case.execute(_cmd(EventType.SESSION_FAILED))
    await use_case.execute(_cmd(EventType.CONVERSATION_USER_INPUT, source=Source.USER))

    session = await repo.get_session("call-1")
    assert session is not None
    assert session.status is SessionStatus.FAILED
    assert len(session.events) == 2


async def test_duplicate_started_is_ignored() -> None:
    repo = InMemoryGovernanceRepository()
    use_case = IngestEvent(repo)

    await use_case.execute(_cmd(EventType.SESSION_STARTED))
    await use_case.execute(_cmd(EventType.SESSION_STARTED))

    session = await repo.get_session("call-1")
    assert session is not None
    assert len(session.events) == 1


async def test_existing_session_is_loaded_through_serialized_append_path() -> None:
    repo = InMemoryGovernanceRepository()
    use_case = IngestEvent(repo)
    await use_case.execute(_cmd(EventType.SESSION_STARTED))
    repo.locked_session_ids.clear()

    await use_case.execute(_cmd(EventType.CONVERSATION_USER_INPUT, source=Source.USER))

    assert repo.locked_session_ids == ["call-1"]


async def test_create_race_reload_ignores_event_for_a_closed_session() -> None:
    class CreateRaceRepository(InMemoryGovernanceRepository):
        def __init__(self) -> None:
            super().__init__()
            self._locked_loads = 0

        async def get_session_for_update(self, session_id: str) -> Session | None:
            self._locked_loads += 1
            if self._locked_loads == 1:
                return None
            return await super().get_session_for_update(session_id)

        async def create_session(self, session: Session) -> bool:
            return False

    repo = CreateRaceRepository()
    closed = Session.open("call-1", uuid4(), datetime.now(UTC))
    closed.record(EventType.SESSION_ENDED, Source.PLATFORM, datetime.now(UTC), {})
    await repo.save_session(closed)

    await IngestEvent(repo).execute(_cmd(EventType.CONVERSATION_USER_INPUT, source=Source.USER))

    assert [event.event_type for event in closed.events] == [EventType.SESSION_ENDED]
