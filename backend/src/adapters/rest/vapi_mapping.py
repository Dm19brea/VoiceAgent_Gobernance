from datetime import UTC, datetime
from typing import Any

from src.application.commands import IngestEventCommand
from src.domain.enums import EventType, Source


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

    return IngestEventCommand(
        call_id=call_id,
        assistant_id=str(assistant_id),
        event_type=event_type,
        source=source,
        timestamp=_timestamp(message),
        payload=message,
    )


def _resolve(vapi_type: str, message: dict[str, Any]) -> tuple[EventType, Source] | None:
    if vapi_type == "status-update":
        status = message.get("status")
        if status == "in-progress":
            return (EventType.SESSION_STARTED, Source.PLATFORM)
        if status == "ended":
            return (EventType.SESSION_ENDED, Source.PLATFORM)
        return None
    if vapi_type == "assistant.started":
        return (EventType.SESSION_STARTED, Source.PLATFORM)
    if vapi_type == "end-of-call-report":
        return (EventType.SESSION_ENDED, Source.PLATFORM)
    if vapi_type in ("speech-update", "conversation-update"):
        role = message.get("role")
        if role == "assistant":
            return (EventType.CONVERSATION_AGENT_RESPONSE, Source.AGENT)
        if role == "user":
            return (EventType.CONVERSATION_USER_INPUT, Source.USER)
        return None
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
