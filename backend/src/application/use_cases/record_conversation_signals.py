"""Application boundary for retry-safe post-terminal conversation signal events."""

import hashlib
import json
import logging
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from src.application.commands import ConversationSignalCommand
from src.application.ports.governance_repository import GovernanceRepository
from src.domain.enums import EventType
from src.domain.event import Event

logger = logging.getLogger(__name__)

_IDENTITY_SCHEMA_VERSION = "conversation-signal/v1"


def canonical_signal_event_id(command: ConversationSignalCommand) -> UUID:
    """Return a UUID5 derived from stable canonical signal identity.

    ``identity_fields`` deliberately carries only the stable outcome fields
    (topic count, goal verdict) — never ``reason`` text, timestamps, or raw
    delivery identifiers — so reprocessing the same report or a provider
    redelivery is a no-op.
    """
    identity = command.identity_fields
    if command.event_type is EventType.CONVERSATION_SILENCE_DETECTED:
        identity = {"detector_version": command.identity_fields.get("detector_version")}
    canonical: dict[str, Any] = {
        "event_type": command.event_type.value,
        "identity": identity,
        "schema_version": _IDENTITY_SCHEMA_VERSION,
        "session_id": command.session_id,
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    fingerprint = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return uuid5(NAMESPACE_URL, f"{_IDENTITY_SCHEMA_VERSION}:{fingerprint}")


class RecordConversationSignals:
    """Append derived conversation signal events without mutating session lifecycle."""

    def __init__(self, repository: GovernanceRepository) -> None:
        self._repo = repository

    async def execute(
        self, session_id: str, commands: list[ConversationSignalCommand]
    ) -> list[Event]:
        if not commands:
            return []

        session = await self._repo.get_session_for_update(session_id)
        if session is None:
            logger.warning(
                "Leaving conversation signals unrecorded: session correlation is unavailable",
                extra={"session_id": session_id},
            )
            return []

        results: list[Event] = []
        for command in commands:
            if command.event_type is EventType.CONVERSATION_SILENCE_DETECTED:
                # Detector versions are immutable and apply only to calls without
                # historical silence evidence. A type-based check under the
                # session row lock prevents reprocessing across version bumps.
                existing_silence = next(
                    (event for event in session.events if event.event_type is command.event_type),
                    None,
                )
                if existing_silence is not None:
                    results.append(existing_silence)
                    continue
            event_id = canonical_signal_event_id(command)
            existing = next((event for event in session.events if event.event_id == event_id), None)
            if existing is not None:
                results.append(existing)
                continue

            payload = dict(command.payload)
            payload["identity"] = str(event_id)
            event = session.append_conversation_signal(
                command.event_type,
                command.source,
                command.timestamp,
                payload,
                event_id=event_id,
            )
            await self._repo.append_event(event)
            results.append(event)

        return results
