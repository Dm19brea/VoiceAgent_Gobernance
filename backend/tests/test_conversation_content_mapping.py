from datetime import UTC, datetime

from src.adapters.rest.vapi_mapping import (
    derive_conversation_content,
    derive_conversation_timed_turns,
)
from src.domain.enums import EventType, Source

_ENDED_AT = datetime(2026, 7, 9, 12, 0, tzinfo=UTC)


def _time_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def test_derives_ordered_content_events_alternating_roles() -> None:
    t0 = datetime(2026, 7, 9, 11, 0, 0, tzinfo=UTC)
    t1 = datetime(2026, 7, 9, 11, 0, 5, tzinfo=UTC)
    report_message = {
        "artifact": {
            "messagesOpenAIFormatted": [
                {"role": "user", "content": "Hi there"},
                {"role": "assistant", "content": "Hello! How can I help?"},
            ],
            "messages": [
                {"role": "user", "message": "Hi there", "time": _time_ms(t0)},
                {"role": "bot", "message": "Hello! How can I help?", "time": _time_ms(t1)},
            ],
        }
    }

    results = derive_conversation_content(report_message, _ENDED_AT)

    assert len(results) == 2
    first, second = results
    assert first[0] is EventType.CONVERSATION_USER_INPUT
    assert first[1] is Source.USER
    assert first[2] == t0
    assert first[3] == "user"
    assert first[4] == "Hi there"
    assert first[5] == 0

    assert second[0] is EventType.CONVERSATION_AGENT_RESPONSE
    assert second[1] is Source.AGENT
    assert second[2] == t1
    assert second[3] == "assistant"
    assert second[4] == "Hello! How can I help?"
    assert second[5] == 1


def test_system_entries_are_skipped_and_not_counted_toward_turn_index() -> None:
    t0 = datetime(2026, 7, 9, 11, 0, 0, tzinfo=UTC)
    report_message = {
        "artifact": {
            "messagesOpenAIFormatted": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Hi"},
            ],
            "messages": [
                {"role": "user", "message": "Hi", "time": _time_ms(t0)},
            ],
        }
    }

    results = derive_conversation_content(report_message, _ENDED_AT)

    assert len(results) == 1
    assert results[0][3] == "user"
    assert results[0][5] == 0


def test_empty_or_missing_messages_open_ai_formatted_is_noop() -> None:
    assert derive_conversation_content({"artifact": {}}, _ENDED_AT) == []
    assert (
        derive_conversation_content({"artifact": {"messagesOpenAIFormatted": []}}, _ENDED_AT) == []
    )
    assert derive_conversation_content({}, _ENDED_AT) == []


def test_consolidates_fragmented_bot_messages_into_one_turn() -> None:
    """messagesOpenAIFormatted is consolidated (1/turn); messages[] is fragmented
    (multiple bot rows per assistant turn). A naive positional zip would misalign
    after the first fragmented turn; role-run consolidation must collapse the
    fragments before matching."""
    t_user = datetime(2026, 7, 9, 11, 0, 0, tzinfo=UTC)
    t_bot_fragment_1 = datetime(2026, 7, 9, 11, 0, 1, tzinfo=UTC)
    t_bot_fragment_2 = datetime(2026, 7, 9, 11, 0, 2, tzinfo=UTC)
    t_user_2 = datetime(2026, 7, 9, 11, 0, 5, tzinfo=UTC)

    report_message = {
        "artifact": {
            "messagesOpenAIFormatted": [
                {"role": "user", "content": "Hi"},
                {"role": "assistant", "content": "Hello! Let me check that for you."},
                {"role": "user", "content": "Thanks"},
            ],
            "messages": [
                {"role": "user", "message": "Hi", "time": _time_ms(t_user)},
                {"role": "bot", "message": "Hello!", "time": _time_ms(t_bot_fragment_1)},
                {
                    "role": "bot",
                    "message": "Let me check that for you.",
                    "time": _time_ms(t_bot_fragment_2),
                },
                {"role": "user", "message": "Thanks", "time": _time_ms(t_user_2)},
            ],
        }
    }

    results = derive_conversation_content(report_message, _ENDED_AT)

    assert len(results) == 3
    assert results[0][2] == t_user
    # consolidated turn keeps the FIRST fragment's time, not the second
    assert results[1][2] == t_bot_fragment_1
    assert results[2][2] == t_user_2


def test_falls_back_to_session_ended_at_when_timing_missing_or_misaligned() -> None:
    report_message = {
        "artifact": {
            "messagesOpenAIFormatted": [
                {"role": "user", "content": "Hi"},
                {"role": "assistant", "content": "Hello!"},
            ],
            "messages": [],
        }
    }

    results = derive_conversation_content(report_message, _ENDED_AT)

    assert len(results) == 2
    assert results[0][2] == _ENDED_AT
    assert results[1][2] == _ENDED_AT


def test_falls_back_when_role_run_is_out_of_order() -> None:
    """If the messages[] role at the aligned position doesn't match the
    formatted-turn role (misalignment), the timestamp falls back rather than
    borrowing a wrong-role timestamp."""
    t_bot = datetime(2026, 7, 9, 11, 0, 1, tzinfo=UTC)
    report_message = {
        "artifact": {
            "messagesOpenAIFormatted": [
                {"role": "user", "content": "Hi"},
            ],
            "messages": [
                {"role": "bot", "message": "unexpected", "time": _time_ms(t_bot)},
            ],
        }
    }

    results = derive_conversation_content(report_message, _ENDED_AT)

    assert len(results) == 1
    assert results[0][2] == _ENDED_AT


def test_timed_turns_use_first_fragment_start_and_final_fragment_end() -> None:
    assistant_start = datetime(2026, 7, 9, 11, 0, 1, tzinfo=UTC)
    assistant_first_end = datetime(2026, 7, 9, 11, 0, 2, tzinfo=UTC)
    assistant_final_start = datetime(2026, 7, 9, 11, 0, 3, tzinfo=UTC)
    assistant_final_end = datetime(2026, 7, 9, 11, 0, 4, tzinfo=UTC)
    user_start = datetime(2026, 7, 9, 11, 0, 10, tzinfo=UTC)
    user_end = datetime(2026, 7, 9, 11, 0, 11, tzinfo=UTC)
    report_message = {
        "artifact": {
            "messagesOpenAIFormatted": [
                {"role": "assistant", "content": "Let me check."},
                {"role": "user", "content": "Thank you."},
            ],
            "messages": [
                {
                    "role": "bot",
                    "time": _time_ms(assistant_start),
                    "endTime": _time_ms(assistant_first_end),
                },
                {
                    "role": "bot",
                    "time": _time_ms(assistant_final_start),
                    "endTime": _time_ms(assistant_final_end),
                },
                {
                    "role": "user",
                    "time": _time_ms(user_start),
                    "endTime": _time_ms(user_end),
                },
            ],
        }
    }

    turns = derive_conversation_timed_turns(report_message)

    assert turns is not None
    assert [(turn.role, turn.turn_index) for turn in turns] == [("assistant", 0), ("user", 1)]
    assert turns[0].started_at == assistant_start
    assert turns[0].ended_at == assistant_final_end
    assert turns[1].started_at == user_start
    assert turns[1].ended_at == user_end


def test_timed_turn_indices_match_content_turn_indices() -> None:
    report_message = {
        "artifact": {
            "messagesOpenAIFormatted": [
                {"role": "system", "content": "Ignore for turn indexing."},
                {"role": "assistant", "content": "Question?"},
                {"role": "user", "content": "Answer."},
            ],
            "messages": [
                {"role": "bot", "time": 1000, "endTime": 2000},
                {"role": "user", "time": 8000, "endTime": 9000},
            ],
        }
    }

    content = derive_conversation_content(report_message, _ENDED_AT)
    turns = derive_conversation_timed_turns(report_message)

    assert turns is not None
    assert [turn.turn_index for turn in turns] == [item[5] for item in content] == [0, 1]
    assert [turn.role for turn in turns] == [item[3] for item in content] == ["assistant", "user"]


def test_invalid_timing_is_normalized_to_none() -> None:
    report_message = {
        "artifact": {
            "messagesOpenAIFormatted": [{"role": "assistant", "content": "Question?"}],
            "messages": [
                {"role": "bot", "time": float("nan"), "endTime": -1},
            ],
        }
    }

    turns = derive_conversation_timed_turns(report_message)

    assert turns is not None
    assert turns[0].started_at is None
    assert turns[0].ended_at is None


def test_timezone_aware_iso_timing_is_accepted() -> None:
    expected_start = datetime(2026, 7, 9, 11, 0, 1, tzinfo=UTC)
    expected_end = datetime(2026, 7, 9, 11, 0, 2, tzinfo=UTC)
    report_message = {
        "artifact": {
            "messagesOpenAIFormatted": [{"role": "assistant", "content": "Question?"}],
            "messages": [
                {
                    "role": "bot",
                    "time": "2026-07-09T11:00:01Z",
                    "endTime": "2026-07-09T11:00:02+00:00",
                }
            ],
        }
    }

    turns = derive_conversation_timed_turns(report_message)

    assert turns is not None
    assert turns[0].started_at == expected_start
    assert turns[0].ended_at == expected_end


def test_naive_bool_infinite_and_overflow_timing_are_rejected() -> None:
    invalid_values = ("2026-07-09T11:00:01", True, float("inf"), 10**400)

    for invalid_value in invalid_values:
        report_message = {
            "artifact": {
                "messagesOpenAIFormatted": [{"role": "assistant", "content": "Question?"}],
                "messages": [{"role": "bot", "time": invalid_value, "endTime": invalid_value}],
            }
        }

        turns = derive_conversation_timed_turns(report_message)

        assert turns is not None
        assert turns[0].started_at is None
        assert turns[0].ended_at is None


def test_timed_turns_fail_closed_on_formatted_raw_role_or_count_mismatch() -> None:
    role_mismatch = {
        "artifact": {
            "messagesOpenAIFormatted": [{"role": "user", "content": "Hello"}],
            "messages": [{"role": "bot", "time": 1000, "endTime": 2000}],
        }
    }
    count_mismatch = {
        "artifact": {
            "messagesOpenAIFormatted": [
                {"role": "assistant", "content": "Question?"},
                {"role": "user", "content": "Answer."},
            ],
            "messages": [{"role": "bot", "time": 1000, "endTime": 2000}],
        }
    }

    assert derive_conversation_timed_turns(role_mismatch) is None
    assert derive_conversation_timed_turns(count_mismatch) is None
