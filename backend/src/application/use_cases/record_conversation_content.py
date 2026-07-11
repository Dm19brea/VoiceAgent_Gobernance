"""Application boundary for retry-safe post-terminal conversation content events."""

import hashlib
import json
import logging
import unicodedata
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from src.application.commands import ConversationContentCommand
from src.application.ports.governance_repository import GovernanceRepository
from src.domain.event import Event

logger = logging.getLogger(__name__)

_IDENTITY_SCHEMA_VERSION = "conversation-content/v1"


def content_sha256(content: str) -> str:
    """Hash NFC-normalized, stripped content so trivial formatting stays stable."""
    normalized = unicodedata.normalize("NFC", content).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def canonical_content_event_id(command: ConversationContentCommand) -> UUID:
    """Return a UUID5 derived from stable canonical content.

    Raw delivery identifiers and timestamps deliberately stay outside the
    fingerprint because both vary across report reprocessing and provider
    redelivery.
    """
    canonical: dict[str, Any] = {
        "event_type": command.event_type.value,
        "identity": {
            "role": command.role,
            "content_sha256": content_sha256(command.content),
            "turn_index": command.turn_index,
        },
        "schema_version": _IDENTITY_SCHEMA_VERSION,
        "session_id": command.session_id,
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    fingerprint = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return uuid5(NAMESPACE_URL, f"{_IDENTITY_SCHEMA_VERSION}:{fingerprint}")


class RecordConversationContent:
    """Append derived conversation content events without mutating session lifecycle."""

    def __init__(self, repository: GovernanceRepository) -> None:
        self._repo = repository

    async def execute(
        self, session_id: str, commands: list[ConversationContentCommand]
    ) -> list[Event]:
        if not commands:
            return []

        session = await self._repo.get_session_for_update(session_id)
        if session is None:
            logger.warning(
                "Leaving conversation content raw-only because session correlation is unavailable",
                extra={"session_id": session_id},
            )
            return []

        results: list[Event] = []
        for command in commands:
            event_id = canonical_content_event_id(command)
            existing = next((event for event in session.events if event.event_id == event_id), None)
            if existing is not None:
                results.append(existing)
                continue

            payload = dict(command.payload)
            payload["identity"] = str(event_id)
            event = session.append_conversation_content(
                command.event_type,
                command.source,
                command.timestamp,
                payload,
                event_id=event_id,
            )
            await self._repo.append_event(event)
            results.append(event)

        return results
