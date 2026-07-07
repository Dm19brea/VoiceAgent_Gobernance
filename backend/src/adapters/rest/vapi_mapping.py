from datetime import UTC, datetime
from typing import Any

from src.application.commands import IngestEventCommand
from src.domain.enums import EventType, Source

_TOOL_CALL_TYPES = {
    "tool-calls",
    "transfer-destination-request",
    "knowledge-base-request",
    "phone-call-control",
    "voice-input",
    "voice-request",
    "call.endpointing.request",
}
_SYSTEM_WARNING_TYPES = {
    "transfer-update",
    "language-change-detected",
    "hang",
}
_SYSTEM_WARNING_PREFIXES = ("chat.", "session.")


def map_vapi_event(webhook: dict[str, Any]) -> IngestEventCommand | None:
    """Translate a Vapi server-message webhook to a canonical ingest command.

    Returns ``None`` when the Vapi type has no canonical mapping (it stays in
    ``raw_events`` but is not promoted to a domain Event) or when the payload
    lacks a call id.
    """
    message: dict[str, Any] = webhook.get("message") or {}
    vapi_type = message.get("type")
    if not isinstance(vapi_type, str):
        return None

    mapping = _resolve(vapi_type, message)
    if mapping is None:
        return None
    event_type, source = mapping

    call: dict[str, Any] = message.get("call") or {}
    call_id = call.get("id")
    if not isinstance(call_id, str) or not call_id:
        return None

    assistant: dict[str, Any] = message.get("assistant") or {}
    assistant_id = call.get("assistantId") or assistant.get("id") or ""

    payload: dict[str, Any] = dict(message)
    if vapi_type == "end-of-call-report":
        payload["report"] = _normalise_report(message)

    return IngestEventCommand(
        call_id=call_id,
        assistant_id=str(assistant_id),
        event_type=event_type,
        source=source,
        timestamp=_timestamp(message),
        payload=payload,
    )


def _normalise_report(message: dict[str, Any]) -> dict[str, Any]:
    """Extract the governance-relevant fields from a Vapi end-of-call-report."""
    return {
        "ended_reason": message.get("endedReason"),
        "duration_seconds": message.get("durationSeconds"),
        "summary": message.get("summary"),
    }


def _resolve(vapi_type: str, message: dict[str, Any]) -> tuple[EventType, Source] | None:
    if vapi_type == "status-update":
        return _resolve_status_update(message)
    if vapi_type == "assistant.started":
        return (EventType.SESSION_STARTED, Source.PLATFORM)
    if vapi_type == "end-of-call-report":
        return (EventType.SESSION_ENDED, Source.PLATFORM)
    if vapi_type == "speech-update":
        return _resolve_speech_update(message)
    if vapi_type == "assistant.speechStarted":
        return (EventType.CONVERSATION_AGENT_RESPONSE, Source.AGENT)
    if vapi_type == "transcript":
        return _resolve_role_message(message)
    if vapi_type == "conversation-update":
        return _resolve_role_message(message)
    if vapi_type == "user-interrupted":
        return (EventType.CONVERSATION_INTERRUPTION_DETECTED, Source.USER)
    if vapi_type in _TOOL_CALL_TYPES:
        return (EventType.TOOL_CALLED, Source.TOOL)
    if vapi_type == "model-output":
        return (EventType.SYSTEM_MODEL_INVOCATION, Source.SYSTEM)
    if vapi_type in _SYSTEM_WARNING_TYPES or vapi_type.startswith(_SYSTEM_WARNING_PREFIXES):
        return (EventType.SYSTEM_WARNING, Source.SYSTEM)
    return None


def _resolve_status_update(message: dict[str, Any]) -> tuple[EventType, Source] | None:
    status = message.get("status")
    if status == "in-progress":
        return (EventType.SESSION_STARTED, Source.PLATFORM)
    return None


def _resolve_speech_update(message: dict[str, Any]) -> tuple[EventType, Source] | None:
    status = message.get("status")
    role_source = _source_from_role(message.get("role"))
    if status == "started":
        return (EventType.CONVERSATION_TURN_STARTED, role_source or Source.PLATFORM)
    if status == "stopped":
        return (EventType.CONVERSATION_TURN_ENDED, role_source or Source.PLATFORM)
    if status is None:
        return _resolve_role_message(message)
    return None


def _resolve_role_message(message: dict[str, Any]) -> tuple[EventType, Source] | None:
    role = message.get("role")
    if role == "assistant":
        return (EventType.CONVERSATION_AGENT_RESPONSE, Source.AGENT)
    if role == "user":
        return (EventType.CONVERSATION_USER_INPUT, Source.USER)
    return None


def _source_from_role(role: object) -> Source | None:
    if role == "assistant":
        return Source.AGENT
    if role == "user":
        return Source.USER
    return None


def _timestamp(message: dict[str, Any]) -> datetime:
    raw = message.get("timestamp")
    if isinstance(raw, int | float):
        return datetime.fromtimestamp(raw / 1000, tz=UTC)
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(UTC)
