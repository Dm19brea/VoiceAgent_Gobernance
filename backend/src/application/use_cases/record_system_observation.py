"""Application boundary for retry-safe post-terminal system observations."""

import hashlib
import json
import logging
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from src.application.commands import SystemObservationCommand
from src.application.ports.governance_repository import GovernanceRepository
from src.domain.enums import EventType
from src.domain.event import Event

logger = logging.getLogger(__name__)

_IDENTITY_SCHEMA_VERSION = "system-observation/v1"
_OBSERVATION_TYPES = frozenset(
    {
        EventType.SYSTEM_LATENCY_MEASURED,
        EventType.SYSTEM_ERROR,
        EventType.SYSTEM_FLAG_RAISED,
    }
)


def canonical_observation_event_id(command: SystemObservationCommand) -> UUID | None:
    """Return a UUID5 derived from stable canonical content, or ``None``.

    Raw delivery identifiers and timestamps deliberately stay outside the
    fingerprint because both vary across provider retries.
    """
    if not command.identity_fields or command.event_type not in _OBSERVATION_TYPES:
        return None
    canonical: dict[str, Any] = {
        "event_type": command.event_type.value,
        "identity": command.identity_fields,
        "schema_version": _IDENTITY_SCHEMA_VERSION,
        "session_id": command.session_id,
    }
    try:
        encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    except (TypeError, ValueError):
        return None
    fingerprint = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return uuid5(NAMESPACE_URL, f"{_IDENTITY_SCHEMA_VERSION}:{fingerprint}")


class RecordSystemObservation:
    """Append allowed system observations without mutating session lifecycle."""

    def __init__(self, repository: GovernanceRepository) -> None:
        self._repo = repository

    async def execute(self, command: SystemObservationCommand) -> Event | None:
        event_id = canonical_observation_event_id(command)
        if event_id is None:
            logger.warning(
                "Leaving system observation raw-only because stable identity is unavailable",
                extra={"session_id": command.session_id, "event_type": command.event_type.value},
            )
            return None

        session = await self._repo.get_session_for_update(command.session_id)
        if session is None:
            logger.warning(
                "Leaving system observation raw-only because session correlation is unavailable",
                extra={"session_id": command.session_id, "event_type": command.event_type.value},
            )
            return None
        existing = next((event for event in session.events if event.event_id == event_id), None)
        if existing is not None:
            return existing

        payload = dict(command.payload)
        payload["identity"] = str(event_id)
        if command.raw_event_id is not None:
            payload["raw_event_id"] = str(command.raw_event_id)
        event = session.append_system_observation(
            command.event_type,
            command.source,
            command.timestamp,
            payload,
            event_id=event_id,
        )
        await self._repo.append_event(event)
        return event
