from typing import Any

import pytest

from src.adapters.rest.vapi_mapping import classify_terminal_event, map_vapi_event
from src.domain.enums import EventType, Source


def _webhook(message: dict[str, Any]) -> dict[str, Any]:
    base = {"type": message["type"], "call": {"id": "call-1", "assistantId": "asst-1"}}
    return {"message": {**base, **message}}


@pytest.mark.parametrize(
    ("message", "event_type", "source"),
    [
        (
            {"type": "status-update", "status": "in-progress"},
            EventType.SESSION_STARTED,
            Source.PLATFORM,
        ),
        ({"type": "assistant.started"}, EventType.SESSION_STARTED, Source.PLATFORM),
        ({"type": "end-of-call-report"}, EventType.SESSION_ENDED, Source.PLATFORM),
        (
            {"type": "speech-update", "status": "started", "role": "user"},
            EventType.CONVERSATION_TURN_STARTED,
            Source.USER,
        ),
        (
            {"type": "speech-update", "status": "stopped", "role": "assistant"},
            EventType.CONVERSATION_TURN_ENDED,
            Source.AGENT,
        ),
        (
            {"type": "speech-update", "role": "assistant"},
            EventType.CONVERSATION_AGENT_RESPONSE,
            Source.AGENT,
        ),
        ({"type": "speech-update", "role": "user"}, EventType.CONVERSATION_USER_INPUT, Source.USER),
        (
            {"type": "assistant.speechStarted"},
            EventType.CONVERSATION_AGENT_RESPONSE,
            Source.AGENT,
        ),
        ({"type": "transcript", "role": "user"}, EventType.CONVERSATION_USER_INPUT, Source.USER),
        (
            {"type": "transcript", "role": "assistant"},
            EventType.CONVERSATION_AGENT_RESPONSE,
            Source.AGENT,
        ),
        ({"type": "user-interrupted"}, EventType.CONVERSATION_INTERRUPTION_DETECTED, Source.USER),
        ({"type": "model-output"}, EventType.SYSTEM_MODEL_INVOCATION, Source.SYSTEM),
        ({"type": "transfer-update"}, EventType.SYSTEM_WARNING, Source.SYSTEM),
        ({"type": "language-change-detected"}, EventType.SYSTEM_WARNING, Source.SYSTEM),
        ({"type": "hang"}, EventType.SYSTEM_WARNING, Source.SYSTEM),
        ({"type": "chat.created"}, EventType.SYSTEM_WARNING, Source.SYSTEM),
        ({"type": "session.updated"}, EventType.SYSTEM_WARNING, Source.SYSTEM),
    ],
)
def test_maps_documented_vapi_server_messages_to_canonical_events(
    message: dict[str, Any], event_type: EventType, source: Source
) -> None:
    result = map_vapi_event(_webhook(message))

    assert result is not None
    assert result.call_id == "call-1"
    assert result.assistant_id == "asst-1"
    assert result.event_type is event_type
    assert result.source is source


@pytest.mark.parametrize(
    "message_type",
    [
        "tool-calls",
        "transfer-destination-request",
        "knowledge-base-request",
        "phone-call-control",
        "voice-input",
    ],
)
def test_tool_webhooks_remain_raw_only(message_type: str) -> None:
    assert map_vapi_event(_webhook({"type": message_type})) is None


def test_maps_end_of_call_report_with_normalized_report_payload() -> None:
    result = map_vapi_event(
        _webhook(
            {
                "type": "end-of-call-report",
                "endedReason": "assistant-ended-call",
                "durationSeconds": 42,
                "summary": "Call summary",
            }
        )
    )

    assert result is not None
    assert result.event_type is EventType.SESSION_ENDED
    assert result.payload["report"] == {
        "ended_reason": "assistant-ended-call",
        "duration_seconds": 42,
        "summary": "Call summary",
        "turn_latencies_seconds": [],
    }


@pytest.mark.parametrize(
    "message",
    [
        {"type": "status-update", "status": "queued"},
        {"type": "status-update", "status": "ended"},
        {"type": "status-update", "status": "failed"},
        {"type": "status-update", "status": "error"},
        {"type": "speech-update", "status": "unknown", "role": "assistant"},
        {"type": "transcript", "role": "system"},
        {"type": "conversation-update", "role": "system"},
        {"type": "conversation-update", "role": "assistant"},
        {"type": "conversation-update", "role": "user"},
        {"type": "assistant-request"},
        {"type": "unknown-type"},
    ],
)
def test_unsupported_or_incomplete_messages_are_not_promoted(message: dict[str, Any]) -> None:
    result = map_vapi_event(_webhook(message))

    assert result is None


def test_message_without_call_id_is_not_promoted() -> None:
    result = map_vapi_event({"message": {"type": "tool-calls"}})

    assert result is None


@pytest.mark.parametrize(
    "ended_reason",
    [
        "customer-ended-call",
        "assistant-ended-call",
        None,
        "",
        123,
        "some-unrecognized-reason",
    ],
)
def test_classify_terminal_event_normal_reasons_end_the_session(ended_reason: object) -> None:
    assert classify_terminal_event(ended_reason) is EventType.SESSION_ENDED


@pytest.mark.parametrize(
    "ended_reason",
    [
        "assistant-error-something",
        "pipeline-fault-detected",
        "PIPELINE-ERROR-OPENAI",
    ],
)
def test_classify_terminal_event_error_substrings_fail_the_session(ended_reason: str) -> None:
    assert classify_terminal_event(ended_reason) is EventType.SESSION_FAILED


@pytest.mark.parametrize(
    "ended_reason",
    [
        "pipeline-no-available-model",
        "call.start.error-vapifault-openai-llm-failed",
        "call.in-progress.error-vapifault-openai-llm-failed",
        "call-start-error-something",
        "twilio-failed-to-connect-call",
        "vonage-disconnected",
        "assistant-request-returned-invalid-response",
    ],
)
def test_classify_terminal_event_prefix_families_fail_the_session(ended_reason: str) -> None:
    assert classify_terminal_event(ended_reason) is EventType.SESSION_FAILED


@pytest.mark.parametrize(
    "ended_reason",
    [
        "pipeline-vapi-voice-failed",
        "pipeline-vapi-transcriber-failed",
        "call.in-progress.error-vapi-transport-never-connected",
        "call.in-progress.error-vapi-worker-crashed",
    ],
)
def test_classify_terminal_event_contains_family_fails_the_session(ended_reason: str) -> None:
    assert classify_terminal_event(ended_reason) is EventType.SESSION_FAILED


@pytest.mark.parametrize(
    "ended_reason",
    [
        "llm-failed",
        "pipeline-no-available-llm-model",
        "phone-call-provider-closed-websocket",
        "worker-shutdown",
        "assistant-not-found",
        "assistant-not-valid",
        "assistant-request-failed",
        "assistant-join-timed-out",
    ],
)
def test_classify_terminal_event_explicit_named_failures_fail_the_session(
    ended_reason: str,
) -> None:
    assert classify_terminal_event(ended_reason) is EventType.SESSION_FAILED


def test_end_of_call_report_with_error_reason_maps_to_session_failed() -> None:
    result = map_vapi_event(
        _webhook(
            {
                "type": "end-of-call-report",
                "endedReason": "pipeline-error-openai-llm-failed",
                "durationSeconds": 12,
                "summary": "Call summary",
            }
        )
    )

    assert result is not None
    assert result.event_type is EventType.SESSION_FAILED
    assert result.payload["report"]["ended_reason"] == "pipeline-error-openai-llm-failed"


def test_classify_terminal_event_does_not_false_positive_on_default() -> None:
    """ "default" contains the substring "fault" as a false cognate; it must not be
    misclassified as a failure just because "fault" appears inside another word."""
    assert classify_terminal_event("customer-selected-default-voice") is EventType.SESSION_ENDED


def test_classify_terminal_event_bare_vapifault_still_fails_the_session() -> None:
    assert classify_terminal_event("vapifault-openai-llm-failed") is EventType.SESSION_FAILED


def test_end_of_call_report_with_normal_reason_still_maps_to_session_ended() -> None:
    result = map_vapi_event(
        _webhook(
            {
                "type": "end-of-call-report",
                "endedReason": "customer-ended-call",
            }
        )
    )

    assert result is not None
    assert result.event_type is EventType.SESSION_ENDED


def test_maps_terminal_failure_to_one_stable_system_error_intent() -> None:
    from uuid import UUID

    from src.adapters.rest.vapi_mapping import map_vapi_system_observations

    raw_event_id = UUID("12345678-1234-5678-1234-567812345678")
    webhook = _webhook(
        {
            "type": "end-of-call-report",
            "endedReason": "pipeline-error-openai-llm-failed",
            "durationSeconds": 12,
            "summary": "Provider pipeline failed",
        }
    )

    observations = map_vapi_system_observations(webhook, raw_event_id)

    assert len(observations) == 1
    observation = observations[0]
    assert observation.event_type is EventType.SYSTEM_ERROR
    assert observation.raw_event_id == raw_event_id
    assert observation.identity_fields == {
        "call_id": "call-1",
        "classification": "terminal_failure",
        "ended_reason": "pipeline-error-openai-llm-failed",
        "report": {
            "duration_seconds": 12,
            "summary": "Provider pipeline failed",
            "turn_latencies_seconds": [],
        },
    }
    assert observation.payload["reason"] == "pipeline-error-openai-llm-failed"


def test_maps_each_normalized_transcript_threat_to_a_stable_flag_intent() -> None:
    from uuid import UUID

    from src.adapters.rest.vapi_mapping import map_vapi_system_observations

    webhook = _webhook(
        {
            "type": "transcript",
            "transcriptType": "final",
            "transcript": "I will hurt you",
            "detectedThreats": [
                {"code": " violence ", "reason": " Threat of harm "},
                {"code": "violence", "reason": "Threat of harm"},
                {"code": "self_harm", "reason": "Self harm mention"},
            ],
        }
    )

    observations = map_vapi_system_observations(
        webhook, UUID("12345678-1234-5678-1234-567812345678")
    )

    assert [(item.payload["code"], item.payload["reason"]) for item in observations] == [
        ("self_harm", "Self harm mention"),
        ("violence", "Threat of harm"),
    ]
    assert observations[0].identity_fields is not None
    assert observations[0].identity_fields["transcript_sha256"] != "I will hurt you"


@pytest.mark.parametrize(
    "message",
    [
        {"type": "voice-request"},
        {"type": "call.endpointing.request"},
        {"type": "unknown-type"},
        {"type": "transcript", "detectedThreats": [{"code": "", "reason": ""}]},
    ],
)
def test_specialized_or_unstable_messages_have_no_system_observation_intent(
    message: dict[str, Any],
) -> None:
    from uuid import UUID

    from src.adapters.rest.vapi_mapping import map_vapi_system_observations

    assert map_vapi_system_observations(_webhook(message), UUID(int=1)) == []


@pytest.mark.parametrize(
    "message", [{"type": "voice-request"}, {"type": "call.endpointing.request"}]
)
def test_specialized_messages_stay_raw_only(message: dict[str, Any]) -> None:
    assert map_vapi_event(_webhook(message)) is None


def test_build_judge_transcript_uses_messages_open_ai_formatted_and_skips_system() -> None:
    from src.adapters.rest.vapi_mapping import build_judge_transcript

    report_message = {
        "artifact": {
            "messagesOpenAIFormatted": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Hi there"},
                {"role": "assistant", "content": "Hello! How can I help?"},
            ]
        }
    }

    transcript = build_judge_transcript(report_message)

    assert "You are a helpful assistant." not in transcript
    assert "Hi there" in transcript
    assert "Hello! How can I help?" in transcript
    lines = [line for line in transcript.splitlines() if line.strip()]
    assert len(lines) == 2


def test_build_judge_transcript_empty_when_no_formatted_messages() -> None:
    from src.adapters.rest.vapi_mapping import build_judge_transcript

    assert build_judge_transcript({"artifact": {}}) == ""
    assert build_judge_transcript({}) == ""


def test_verdict_to_signal_commands_emits_topic_change_and_goal_achieved() -> None:
    from datetime import UTC, datetime

    from src.adapters.rest.vapi_mapping import verdict_to_signal_commands
    from src.application.ports.conversation_judge import JudgeVerdict
    from src.domain.enums import EventType, Source

    verdict = JudgeVerdict(
        topic_change_count=3,
        topics=["billing", "cancellation", "retention"],
        topic_reason="shifted three times",
        goal_achieved=True,
        goal_reason="issue resolved",
    )
    timestamp = datetime(2026, 7, 9, 12, 0, tzinfo=UTC)

    commands = verdict_to_signal_commands(verdict, "call-1", timestamp)

    assert len(commands) == 2
    topic_command = next(c for c in commands if c.event_type is EventType.CONVERSATION_TOPIC_CHANGE)
    goal_command = next(c for c in commands if c.event_type is EventType.CONVERSATION_GOAL_ACHIEVED)
    assert topic_command.source is Source.PLATFORM
    assert topic_command.payload["count"] == 3
    assert topic_command.payload["topics"] == ["billing", "cancellation", "retention"]
    assert goal_command.source is Source.PLATFORM
    assert goal_command.payload["reason"] == "issue resolved"
    assert all(c.session_id == "call-1" and c.timestamp == timestamp for c in commands)


def test_verdict_to_signal_commands_zero_topic_changes_emits_no_topic_command() -> None:
    from datetime import UTC, datetime

    from src.adapters.rest.vapi_mapping import verdict_to_signal_commands
    from src.application.ports.conversation_judge import JudgeVerdict
    from src.domain.enums import EventType

    verdict = JudgeVerdict(
        topic_change_count=0,
        topics=[],
        topic_reason=None,
        goal_achieved=True,
        goal_reason="information-only call",
    )

    commands = verdict_to_signal_commands(verdict, "call-1", datetime(2026, 7, 9, tzinfo=UTC))

    assert len(commands) == 1
    assert commands[0].event_type is EventType.CONVERSATION_GOAL_ACHIEVED


def test_verdict_to_signal_commands_goal_failed_never_emits_goal_achieved() -> None:
    from datetime import UTC, datetime

    from src.adapters.rest.vapi_mapping import verdict_to_signal_commands
    from src.application.ports.conversation_judge import JudgeVerdict
    from src.domain.enums import EventType

    verdict = JudgeVerdict(
        topic_change_count=0,
        topics=[],
        topic_reason=None,
        goal_achieved=False,
        goal_reason="issue unresolved",
    )

    commands = verdict_to_signal_commands(verdict, "call-1", datetime(2026, 7, 9, tzinfo=UTC))

    event_types = [c.event_type for c in commands]
    assert EventType.CONVERSATION_GOAL_FAILED in event_types
    assert EventType.CONVERSATION_GOAL_ACHIEVED not in event_types
