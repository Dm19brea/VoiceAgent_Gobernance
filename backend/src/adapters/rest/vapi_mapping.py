import hashlib
from dataclasses import replace
from datetime import UTC, datetime
from math import isfinite
from typing import Any
from uuid import UUID

from src.application.commands import (
    ConversationSignalCommand,
    IngestEventCommand,
    SystemObservationCommand,
)
from src.application.ports.conversation_judge import JudgeVerdict
from src.application.use_cases.detect_conversation_silence import TimedTurn
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


def derive_conversation_content(
    report_message: dict[str, Any], session_ended_at: datetime
) -> list[tuple[EventType, Source, datetime, str, str, int, dict[str, Any]]]:
    """Derive ordered content-event tuples from an end-of-call-report ``message``.

    Iterates ``artifact.messagesOpenAIFormatted`` (consolidated, one entry per
    turn) in order, skipping ``system`` entries. Each turn's timestamp is
    aligned against ``artifact.messages`` (fragmented, multiple bot rows per
    assistant turn) by first consolidating consecutive same-role fragments
    into one boundary-per-turn list, then matching role-by-role at the same
    position. Falls back to ``session_ended_at`` when timing is missing or
    the aligned role does not match (misalignment).

    Returns tuples of ``(event_type, source, timestamp, role, content,
    turn_index, payload)`` in report order. ``turn_index`` counts only
    non-system turns.
    """
    artifact = report_message.get("artifact")
    if not isinstance(artifact, dict):
        return []
    formatted = artifact.get("messagesOpenAIFormatted")
    if not isinstance(formatted, list) or not formatted:
        return []

    raw_messages = artifact.get("messages")
    turns = _consolidate_messages_by_turn(raw_messages if isinstance(raw_messages, list) else [])

    results: list[tuple[EventType, Source, datetime, str, str, int, dict[str, Any]]] = []
    turn_index = 0
    for entry in formatted:
        if not isinstance(entry, dict):
            continue
        role = entry.get("role")
        content = entry.get("content")
        if role not in ("assistant", "user") or not isinstance(content, str):
            continue

        timestamp = session_ended_at
        if turn_index < len(turns):
            aligned_turn = turns[turn_index]
            if aligned_turn.role == role and aligned_turn.started_at is not None:
                timestamp = aligned_turn.started_at

        event_type = (
            EventType.CONVERSATION_AGENT_RESPONSE
            if role == "assistant"
            else EventType.CONVERSATION_USER_INPUT
        )
        source = Source.AGENT if role == "assistant" else Source.USER
        payload = {"content": content, "role": role, "turn_index": turn_index}
        results.append((event_type, source, timestamp, role, content, turn_index, payload))
        turn_index += 1

    return results


def derive_conversation_timed_turns(report_message: dict[str, Any]) -> tuple[TimedTurn, ...] | None:
    """Return strictly aligned turn boundaries for silence derivation.

    Content persistence may fall back to the terminal timestamp, but silence
    evidence must fail closed unless the formatted and raw turn sequences agree
    exactly in both count and role.
    """
    artifact = report_message.get("artifact")
    if not isinstance(artifact, dict):
        return None

    formatted = artifact.get("messagesOpenAIFormatted")
    raw_messages = artifact.get("messages")
    if not isinstance(formatted, list) or not isinstance(raw_messages, list):
        return None

    formatted_roles = [
        entry.get("role")
        for entry in formatted
        if isinstance(entry, dict)
        and entry.get("role") in ("assistant", "user")
        and isinstance(entry.get("content"), str)
    ]
    turns = _consolidate_messages_by_turn(raw_messages)
    if len(formatted_roles) != len(turns):
        return None
    if any(role != turn.role for role, turn in zip(formatted_roles, turns, strict=True)):
        return None
    return tuple(turns)


def _consolidate_messages_by_turn(messages: list[Any]) -> list[TimedTurn]:
    """Collapse consecutive same-role ``messages[]`` fragments into one turn.

    ``messages`` is fragmented (Vapi can emit multiple bot rows per assistant
    turn); ``messagesOpenAIFormatted`` is consolidated (one row per turn). A
    naive positional zip between the two therefore misaligns after the first
    fragmented turn. This groups consecutive same-role rows into a single
    turn, keeping the first fragment's ``time`` and final fragment's
    ``endTime``, so the result lines up positionally with
    ``messagesOpenAIFormatted``.
    """
    turns: list[TimedTurn] = []
    last_role: str | None = None
    for entry in messages:
        if not isinstance(entry, dict):
            continue
        role = _normalise_report_message_role(entry.get("role"))
        if role is None:
            continue
        if role == last_role:
            turns[-1] = replace(turns[-1], ended_at=_parse_report_time(entry.get("endTime")))
            continue
        turns.append(
            TimedTurn(
                role=role,
                turn_index=len(turns),
                started_at=_parse_report_time(entry.get("time")),
                ended_at=_parse_report_time(entry.get("endTime")),
            )
        )
        last_role = role
    return turns


def _normalise_report_message_role(raw_role: object) -> str | None:
    if raw_role == "bot":
        return "assistant"
    if raw_role == "user":
        return "user"
    return None


def _parse_report_time(raw: object) -> datetime | None:
    parsed: datetime
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int | float):
        if (isinstance(raw, float) and not isfinite(raw)) or raw < 0:
            return None
        try:
            parsed = datetime.fromtimestamp(raw / 1000, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    elif isinstance(raw, str):
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return None
    try:
        timestamp = parsed.astimezone(UTC).timestamp()
    except (OverflowError, OSError, ValueError):
        return None
    return parsed if isfinite(timestamp) and timestamp >= 0 else None


def build_judge_transcript(report_message: dict[str, Any]) -> str:
    """Build a plain-text transcript for the LLM judge from the SAME source
    used by ``derive_conversation_content`` (``artifact.messagesOpenAIFormatted``),
    skipping ``system`` entries.

    Returns an empty string when there is nothing to judge.
    """
    artifact = report_message.get("artifact")
    if not isinstance(artifact, dict):
        return ""
    formatted = artifact.get("messagesOpenAIFormatted")
    if not isinstance(formatted, list) or not formatted:
        return ""

    lines: list[str] = []
    for entry in formatted:
        if not isinstance(entry, dict):
            continue
        role = entry.get("role")
        content = entry.get("content")
        if role not in ("assistant", "user") or not isinstance(content, str):
            continue
        speaker = "agent" if role == "assistant" else "caller"
        lines.append(f"{speaker}: {content}")

    return "\n".join(lines)


def verdict_to_signal_commands(
    verdict: JudgeVerdict, session_id: str, timestamp: datetime
) -> list[ConversationSignalCommand]:
    """Translate a ``JudgeVerdict`` into retry-safe signal commands.

    Emits at most one ``conversation.topic_change`` command (only when
    ``topic_change_count > 0``) and exactly one mutually-exclusive
    ``conversation.goal_achieved`` / ``conversation.goal_failed`` command.
    ``identity_fields`` carries only the stable outcome fields, never
    ``reason`` text or timestamps.
    """
    commands: list[ConversationSignalCommand] = []

    if verdict.topic_change_count > 0:
        topic_payload: dict[str, Any] = {
            "count": verdict.topic_change_count,
            "topics": verdict.topics,
        }
        if verdict.topic_reason:
            topic_payload["reason"] = verdict.topic_reason
        commands.append(
            ConversationSignalCommand(
                session_id=session_id,
                event_type=EventType.CONVERSATION_TOPIC_CHANGE,
                source=Source.PLATFORM,
                timestamp=timestamp,
                identity_fields={"count": verdict.topic_change_count},
                payload=topic_payload,
            )
        )

    goal_event_type = (
        EventType.CONVERSATION_GOAL_ACHIEVED
        if verdict.goal_achieved
        else EventType.CONVERSATION_GOAL_FAILED
    )
    commands.append(
        ConversationSignalCommand(
            session_id=session_id,
            event_type=goal_event_type,
            source=Source.PLATFORM,
            timestamp=timestamp,
            identity_fields={"verdict": "achieved" if verdict.goal_achieved else "failed"},
            payload={"reason": verdict.goal_reason},
        )
    )

    return commands


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
