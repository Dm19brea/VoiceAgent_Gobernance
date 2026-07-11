from datetime import UTC, datetime
from uuid import uuid4

from pytest import LogCaptureFixture

from src.application.commands import ConversationContentCommand
from src.application.use_cases.record_conversation_content import (
    RecordConversationContent,
    canonical_content_event_id,
)
from src.domain.enums import EventType, SessionStatus, Source
from src.domain.session import Session
from tests.fakes import InMemoryGovernanceRepository


def _command(
    *,
    role: str = "assistant",
    content: str = "Hello there",
    turn_index: int = 0,
    timestamp: datetime | None = None,
    session_id: str = "call-content",
) -> ConversationContentCommand:
    event_type = (
        EventType.CONVERSATION_AGENT_RESPONSE
        if role == "assistant"
        else EventType.CONVERSATION_USER_INPUT
    )
    source = Source.AGENT if role == "assistant" else Source.USER
    return ConversationContentCommand(
        session_id=session_id,
        event_type=event_type,
        source=source,
        timestamp=timestamp or datetime.now(UTC),
        role=role,
        content=content,
        turn_index=turn_index,
        payload={"content": content},
    )


def test_canonical_content_identity_is_timestamp_independent_and_input_specific() -> None:
    first = _command(timestamp=datetime(2026, 7, 9, 10, tzinfo=UTC))
    retry = _command(timestamp=datetime(2026, 7, 9, 11, tzinfo=UTC))
    distinct_turn = _command(turn_index=1)
    distinct_content = _command(content="Something else")

    assert canonical_content_event_id(first) == canonical_content_event_id(retry)
    assert canonical_content_event_id(first) != canonical_content_event_id(distinct_turn)
    assert canonical_content_event_id(first) != canonical_content_event_id(distinct_content)


def test_canonical_content_identity_normalizes_whitespace_but_not_case() -> None:
    padded = _command(content="  Hello there  ")
    unpadded = _command(content="Hello there")
    different_case = _command(content="hello there")

    assert canonical_content_event_id(padded) == canonical_content_event_id(unpadded)
    assert canonical_content_event_id(padded) != canonical_content_event_id(different_case)


async def test_record_conversation_content_appends_ordered_events() -> None:
    repo = InMemoryGovernanceRepository()
    session = Session.open("call-content", uuid4(), datetime.now(UTC))
    ended_at = datetime.now(UTC)
    session.record(EventType.SESSION_ENDED, Source.PLATFORM, ended_at, {})
    await repo.save_session(session)
    use_case = RecordConversationContent(repo)

    commands = [
        _command(role="user", content="Hi", turn_index=0),
        _command(role="assistant", content="Hello!", turn_index=1),
    ]

    results = await use_case.execute("call-content", commands)

    assert [event.event_type for event in results] == [
        EventType.CONVERSATION_USER_INPUT,
        EventType.CONVERSATION_AGENT_RESPONSE,
    ]
    assert session.status is SessionStatus.ENDED
    assert session.ended_at == ended_at
    assert [event.event_type for event in session.events] == [
        EventType.SESSION_ENDED,
        EventType.CONVERSATION_USER_INPUT,
        EventType.CONVERSATION_AGENT_RESPONSE,
    ]


async def test_record_conversation_content_is_idempotent_on_redelivery() -> None:
    repo = InMemoryGovernanceRepository()
    session = Session.open("call-content", uuid4(), datetime.now(UTC))
    session.record(EventType.SESSION_ENDED, Source.PLATFORM, datetime.now(UTC), {})
    await repo.save_session(session)
    use_case = RecordConversationContent(repo)
    commands = [_command(role="user", content="Hi", turn_index=0)]

    first = await use_case.execute("call-content", commands)
    retry = await use_case.execute(
        "call-content",
        [_command(role="user", content="Hi", turn_index=0, timestamp=datetime.now(UTC))],
    )

    assert len(first) == 1
    assert [event.event_id for event in retry] == [event.event_id for event in first]
    assert len(session.events) == 2  # SESSION_ENDED + 1 content event, no duplicate


async def test_record_conversation_content_session_not_found_is_noop(
    caplog: LogCaptureFixture,
) -> None:
    repo = InMemoryGovernanceRepository()
    use_case = RecordConversationContent(repo)

    results = await use_case.execute("missing-session", [_command(session_id="missing-session")])

    assert results == []
    assert "session correlation" in caplog.text or "session" in caplog.text.lower()
