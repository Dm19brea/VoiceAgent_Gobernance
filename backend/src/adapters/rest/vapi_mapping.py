import hashlib
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from src.application.commands import IngestEventCommand, SystemObservationCommand
from src.domain.enums import EventType, Source

_TOOL_CALL_TYPES = {
    "tool-calls",
    "transfer-destination-request",
    "knowledge-base-request",
    "phone-call-control",
    "voice-input",
}
_SYSTEM_WARNING_TYPES = {
    "transfer-update",
    "language-change-detected",
    "hang",
}
_SYSTEM_WARNING_PREFIXES = ("chat.", "session.")

_FAILURE_SUBSTRINGS = ("error", "vapifault")
_FAILURE_PREFIXES = (
    "pipeline-",
    "call.start.error-",
    "call.in-progress.error-",
    "call-start-error-",
    "twilio-",
    "vonage-",
    "assistant-request-returned-",
)
_FAILURE_CONTAINS = (
    "-voice-failed",
    "-transcriber-failed",
    "-transport-",
    "-worker-",
)
_FAILURE_REASONS = frozenset(
    {
        "llm-failed",
        "pipeline-no-available-llm-model",
        "phone-call-provider-closed-websocket",
        "worker-shutdown",
        "assistant-not-found",
        "assistant-not-valid",
        "assistant-request-failed",
        "assistant-join-timed-out",
    }
)


def classify_terminal_event(ended_reason: object) -> EventType:
    """Classify a Vapi ``end-of-call-report`` ``endedReason`` as failed or ended.

    Fail-safe by default: only recognized error signals resolve to
    ``SESSION_FAILED``; anything else (including ``None`` and unknown
    strings) resolves to ``SESSION_ENDED``.
    """
    if not isinstance(ended_reason, str) or not ended_reason:
        return EventType.SESSION_ENDED

    reason = ended_reason.lower()

    if reason in _FAILURE_REASONS:
        return EventType.SESSION_FAILED
    if any(substring in reason for substring in _FAILURE_SUBSTRINGS):
        return EventType.SESSION_FAILED
    if reason.startswith(_FAILURE_PREFIXES):
        return EventType.SESSION_FAILED
    if any(fragment in reason for fragment in _FAILURE_CONTAINS):
        return EventType.SESSION_FAILED

    return EventType.SESSION_ENDED


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


def map_vapi_system_observations(
    webhook: dict[str, Any], raw_event_id: UUID
) -> list[SystemObservationCommand]:
    """Translate safe Vapi derivatives to retry-safe system observations.

    The raw event id is retained solely as provenance.  Stable provider fields
    make up ``identity_fields`` so a Vapi redelivery creates the same canonical
    event even though it lands as a new raw row.
    """
    message: dict[str, Any] = webhook.get("message") or {}
    vapi_type = message.get("type")
    call: dict[str, Any] = message.get("call") or {}
    call_id = call.get("id")
    if not isinstance(vapi_type, str) or not isinstance(call_id, str) or not call_id:
        return []

    if vapi_type == "end-of-call-report":
        return _terminal_error_observations(message, call_id, raw_event_id)
    if vapi_type == "transcript":
        return _threat_observations(message, call_id, raw_event_id)
    return []


def _terminal_error_observations(
    message: dict[str, Any], call_id: str, raw_event_id: UUID
) -> list[SystemObservationCommand]:
    ended_reason = message.get("endedReason")
    if classify_terminal_event(ended_reason) is not EventType.SESSION_FAILED:
        return []
    if not isinstance(ended_reason, str) or not ended_reason:
        return []

    report = _normalise_report(message)
    identity_report = {
        key: value for key, value in report.items() if key != "ended_reason" and value is not None
    }
    return [
        SystemObservationCommand(
            session_id=call_id,
            event_type=EventType.SYSTEM_ERROR,
            source=Source.SYSTEM,
            timestamp=_timestamp(message),
            identity_fields={
                "call_id": call_id,
                "classification": "terminal_failure",
                "ended_reason": ended_reason.strip().lower(),
                "report": identity_report,
            },
            raw_event_id=raw_event_id,
            payload={
                "classification": "terminal_failure",
                "reason": ended_reason,
                "report": report,
                "provider": "vapi",
            },
        )
    ]


def _threat_observations(
    message: dict[str, Any], call_id: str, raw_event_id: UUID
) -> list[SystemObservationCommand]:
    transcript = message.get("transcript")
    transcript_type = message.get("transcriptType")
    if (
        not isinstance(transcript, str)
        or not transcript.strip()
        or not isinstance(transcript_type, str)
    ):
        return []

    transcript_hash = hashlib.sha256(transcript.strip().encode("utf-8")).hexdigest()
    observations: list[SystemObservationCommand] = []
    for code, reason in _normalise_threats(message.get("detectedThreats")):
        observations.append(
            SystemObservationCommand(
                session_id=call_id,
                event_type=EventType.SYSTEM_FLAG_RAISED,
                source=Source.SYSTEM,
                timestamp=_timestamp(message),
                identity_fields={
                    "call_id": call_id,
                    "code": code,
                    "reason": reason,
                    "transcript_sha256": transcript_hash,
                    "transcript_type": transcript_type.strip().lower(),
                },
                raw_event_id=raw_event_id,
                payload={
                    "code": code,
                    "reason": reason,
                    "provider": "vapi",
                    "transcript_type": transcript_type,
                },
            )
        )
    return observations


def _normalise_threats(raw_threats: object) -> list[tuple[str, str]]:
    if not isinstance(raw_threats, list):
        return []
    findings: set[tuple[str, str]] = set()
    for threat in raw_threats:
        if not isinstance(threat, dict):
            continue
        raw_code, raw_reason = threat.get("code"), threat.get("reason")
        if not isinstance(raw_code, str) or not isinstance(raw_reason, str):
            continue
        code, reason = raw_code.strip().lower(), raw_reason.strip()
        if code and reason:
            findings.add((code, reason))
    return sorted(findings)


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
        return (classify_terminal_event(message.get("endedReason")), Source.PLATFORM)
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
