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
        (
            {"type": "conversation-update", "role": "assistant"},
            EventType.CONVERSATION_AGENT_RESPONSE,
            Source.AGENT,
        ),
        (
            {"type": "conversation-update", "role": "user"},
            EventType.CONVERSATION_USER_INPUT,
            Source.USER,
        ),
        ({"type": "user-interrupted"}, EventType.CONVERSATION_INTERRUPTION_DETECTED, Source.USER),
        ({"type": "tool-calls"}, EventType.TOOL_CALLED, Source.TOOL),
        ({"type": "transfer-destination-request"}, EventType.TOOL_CALLED, Source.TOOL),
        ({"type": "knowledge-base-request"}, EventType.TOOL_CALLED, Source.TOOL),
        ({"type": "phone-call-control"}, EventType.TOOL_CALLED, Source.TOOL),
        ({"type": "voice-input"}, EventType.TOOL_CALLED, Source.TOOL),
        ({"type": "voice-request"}, EventType.TOOL_CALLED, Source.TOOL),
        ({"type": "call.endpointing.request"}, EventType.TOOL_CALLED, Source.TOOL),
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
    """"default" contains the substring "fault" as a false cognate; it must not be
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
