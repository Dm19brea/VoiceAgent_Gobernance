from datetime import UTC, datetime
from uuid import uuid4

from pytest import LogCaptureFixture

from src.application.commands import ConversationSignalCommand
from src.application.use_cases.record_conversation_signals import (
    RecordConversationSignals,
    canonical_signal_event_id,
)
from src.domain.enums import EventType, SessionStatus, Source
from src.domain.session import Session
from tests.fakes import InMemoryGovernanceRepository


def _topic_command(
    *,
    count: int = 3,
    topics: list[str] | None = None,
    timestamp: datetime | None = None,
    session_id: str = "call-signal",
) -> ConversationSignalCommand:
    return ConversationSignalCommand(
        session_id=session_id,
        event_type=EventType.CONVERSATION_TOPIC_CHANGE,
        source=Source.PLATFORM,
        timestamp=timestamp or datetime.now(UTC),
        identity_fields={"count": count},
        payload={"count": count, "topics": topics or ["billing", "cancellation"]},
    )


def _goal_command(
    *,
    verdict: str = "achieved",
    reason: str = "resolved",
    timestamp: datetime | None = None,
    session_id: str = "call-signal",
) -> ConversationSignalCommand:
    event_type = (
        EventType.CONVERSATION_GOAL_ACHIEVED
        if verdict == "achieved"
        else EventType.CONVERSATION_GOAL_FAILED
    )
    return ConversationSignalCommand(
        session_id=session_id,
        event_type=event_type,
        source=Source.PLATFORM,
        timestamp=timestamp or datetime.now(UTC),
        identity_fields={"verdict": verdict},
        payload={"reason": reason},
    )


def test_canonical_signal_identity_is_stable_across_retries() -> None:
    first = _topic_command(timestamp=datetime(2026, 7, 9, 10, tzinfo=UTC))
    retry = _topic_command(timestamp=datetime(2026, 7, 9, 11, tzinfo=UTC))

    assert canonical_signal_event_id(first) == canonical_signal_event_id(retry)


def test_canonical_topic_identity_ignores_topics_and_reason_keys_only_count() -> None:
    baseline = _topic_command(count=3, topics=["billing", "cancellation"])
    different_topics_same_count = _topic_command(count=3, topics=["retention", "billing"])
    different_count = _topic_command(count=2, topics=["billing", "cancellation"])

    assert canonical_signal_event_id(baseline) == canonical_signal_event_id(
        different_topics_same_count
    )
    assert canonical_signal_event_id(baseline) != canonical_signal_event_id(different_count)


def test_canonical_goal_identity_ignores_reason_only_verdict() -> None:
    achieved_a = _goal_command(verdict="achieved", reason="resolved quickly")
    achieved_b = _goal_command(verdict="achieved", reason="totally different reason text")
    failed = _goal_command(verdict="failed", reason="resolved quickly")

    assert canonical_signal_event_id(achieved_a) == canonical_signal_event_id(achieved_b)
    assert canonical_signal_event_id(achieved_a) != canonical_signal_event_id(failed)


async def test_record_conversation_signals_appends_events() -> None:
    repo = InMemoryGovernanceRepository()
    session = Session.open("call-signal", uuid4(), datetime.now(UTC))
    ended_at = datetime.now(UTC)
    session.record(EventType.SESSION_ENDED, Source.PLATFORM, ended_at, {})
    await repo.save_session(session)
    use_case = RecordConversationSignals(repo)

    commands = [_topic_command(), _goal_command()]

    results = await use_case.execute("call-signal", commands)

    assert [event.event_type for event in results] == [
        EventType.CONVERSATION_TOPIC_CHANGE,
        EventType.CONVERSATION_GOAL_ACHIEVED,
    ]
    assert session.status is SessionStatus.ENDED
    assert session.ended_at == ended_at


async def test_record_conversation_signals_is_idempotent_on_redelivery() -> None:
    repo = InMemoryGovernanceRepository()
    session = Session.open("call-signal", uuid4(), datetime.now(UTC))
    session.record(EventType.SESSION_ENDED, Source.PLATFORM, datetime.now(UTC), {})
    await repo.save_session(session)
    use_case = RecordConversationSignals(repo)
    commands = [_topic_command(), _goal_command()]

    first = await use_case.execute("call-signal", commands)
    retry = await use_case.execute(
        "call-signal",
        [
            _topic_command(timestamp=datetime.now(UTC)),
            _goal_command(timestamp=datetime.now(UTC)),
        ],
    )

    assert len(first) == 2
    assert [event.event_id for event in retry] == [event.event_id for event in first]
    assert len(session.events) == 3  # SESSION_ENDED + topic + goal, no duplicates


async def test_record_conversation_signals_session_not_found_is_noop(
    caplog: LogCaptureFixture,
) -> None:
    repo = InMemoryGovernanceRepository()
    use_case = RecordConversationSignals(repo)

    results = await use_case.execute(
        "missing-session", [_topic_command(session_id="missing-session")]
    )

    assert results == []
    assert "session" in caplog.text.lower()
