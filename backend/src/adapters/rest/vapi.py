import hmac
from datetime import UTC, datetime
from time import perf_counter
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from loguru import logger
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.rest.vapi_mapping import (
    extract_assistant_id,
    map_vapi_event,
    map_vapi_system_observations,
)
from src.application.commands import IngestEventCommand, SystemObservationCommand
from src.application.use_cases.ingest_event import IngestEvent
from src.application.use_cases.record_system_observation import RecordSystemObservation
from src.domain.enums import EventType, Source
from src.domain.event import Event
from src.domain.secrets import SecretResolver
from src.infrastructure.celery.tasks import build_session_evidences
from src.infrastructure.db.models import RawEvent
from src.infrastructure.db.session import async_session_maker, get_session
from src.infrastructure.redis.active_sessions import (
    get_active_session_store,
    update_active_state,
)
from src.infrastructure.repositories.credentials_repository import CredentialsRepository
from src.infrastructure.repositories.governance_repository import SqlAlchemyGovernanceRepository

router = APIRouter()

_TERMINAL_EVENTS = (EventType.SESSION_ENDED, EventType.SESSION_FAILED)

# Turn lifecycle (from ``speech-update``) drives only the real-time speaking
# indicator via ``update_active_state``; it is intentionally NOT persisted as a
# canonical governance event. Conversation content is derived post-terminal from
# the end-of-call-report instead.
_LIVE_ONLY_EVENTS = (EventType.CONVERSATION_TURN_STARTED, EventType.CONVERSATION_TURN_ENDED)

SessionDep = Annotated[AsyncSession, Depends(get_session)]


class VapiMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str


class VapiWebhook(BaseModel):
    """Vapi server-message envelope. Unknown fields are kept (extra=allow)."""

    model_config = ConfigDict(extra="allow")

    message: VapiMessage


@router.post("/webhooks/vapi", status_code=200)
async def vapi_webhook(
    webhook: VapiWebhook,
    session: SessionDep,
    vapi_secret: Annotated[str | None, Header(alias="x-vapi-secret")] = None,
) -> dict[str, str]:
    """Receive a Vapi webhook and persist it only for a governed agent (M2.7, R3).

    A governed agent (registered, non-deleted) is resolved by ``assistantId``
    BEFORE anything is persisted. Calls for an unknown or soft-deleted
    assistant are discarded entirely: no ``raw_events`` row, no Session/Event,
    no downstream Celery/Redis/latency side effects. A registered agent whose
    ``webhook_activated`` flag is ``False`` is rejected with 403 and, likewise,
    nothing is persisted. For a governed and activated agent, the raw body is
    landed in ``raw_events`` (immutable landing) and, if the Vapi type maps to
    a canonical event, promoted into the Session/Event trace, exactly as
    before this change. Requests without a matching configured secret are
    rejected before lookup, activation check, or persistence.
    """
    configured_secret = await SecretResolver(CredentialsRepository(session)).webhook_secret()
    if (
        not configured_secret
        or vapi_secret is None
        or not hmac.compare_digest(vapi_secret, configured_secret)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Vapi webhook secret",
        )

    event_type = webhook.message.type
    raw = webhook.model_dump(mode="json")
    receipt_started = perf_counter()
    receipt_at = datetime.now(UTC)
    logger.info("Vapi webhook received: type={}", event_type)

    repository = SqlAlchemyGovernanceRepository(session)
    assistant_id = extract_assistant_id(raw)
    agent = await repository.get_agent_by_assistant_id(assistant_id) if assistant_id else None
    if agent is None:
        logger.info(
            "Vapi webhook discarded for ungoverned assistant: type={} assistant_id={}",
            event_type,
            assistant_id,
        )
        return {"status": "ignored"}

    if not agent.webhook_activated:
        logger.info(
            "Vapi webhook rejected for not-activated assistant: type={} assistant_id={}",
            event_type,
            assistant_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El agente no tiene las credenciales configuradas",
        )

    canonical_event: Event | None = None
    command: IngestEventCommand | None = None
    try:
        raw_event = RawEvent(event_type=event_type, payload=raw)
        session.add(raw_event)
        await session.flush()

        command = map_vapi_event(raw)
        if command is not None and command.event_type not in _LIVE_ONLY_EVENTS:
            canonical_event = await IngestEvent(repository).execute(command)
        for observation in map_vapi_system_observations(raw, raw_event.id):
            await RecordSystemObservation(repository).execute(observation)
        await session.commit()
    except Exception:
        await session.rollback()
        logger.exception("Vapi webhook persistence failed: type={}", event_type)
        raise

    if (
        command is not None
        and canonical_event is not None
        and canonical_event.event_type in _TERMINAL_EVENTS
    ):
        await _record_webhook_ingestion_latency(
            session_id=command.call_id,
            canonical_event=canonical_event,
            raw_event_id=raw_event.id,
            receipt_at=receipt_at,
            completion_at=datetime.now(UTC),
            duration_milliseconds=(perf_counter() - receipt_started) * 1000,
        )

    # Session closed: build its evidences asynchronously (does not block the response).
    # A broker failure must not break ingestion, so the enqueue is best-effort.
    if command is not None and command.event_type in _TERMINAL_EVENTS:
        try:
            build_session_evidences.delay(command.call_id)
        except Exception:
            logger.exception("Failed to enqueue evidence build: session={}", command.call_id)

    # Reflect the session in the live active-session store. Best-effort: a Redis
    # failure must not break ingestion (the source of truth stays in Postgres).
    if command is not None:
        try:
            await update_active_state(
                get_active_session_store(),
                SqlAlchemyGovernanceRepository(session),
                command,
            )
        except Exception:
            logger.exception("Failed to update active-session state: session={}", command.call_id)

    logger.info("Vapi webhook persisted: type={}", event_type)
    return {"status": "received"}


async def _record_webhook_ingestion_latency(
    *,
    session_id: str,
    canonical_event: Event,
    raw_event_id: UUID,
    receipt_at: datetime,
    completion_at: datetime,
    duration_milliseconds: float,
) -> None:
    """Persist local webhook timing after the main transaction, best-effort only."""
    try:
        async with async_session_maker() as observation_session:
            repository = SqlAlchemyGovernanceRepository(observation_session)
            await RecordSystemObservation(repository).execute(
                SystemObservationCommand(
                    session_id=session_id,
                    event_type=EventType.SYSTEM_LATENCY_MEASURED,
                    source=Source.SYSTEM,
                    timestamp=completion_at,
                    identity_fields={
                        "canonical_event_id": str(canonical_event.event_id),
                        "operation": "webhook_ingestion",
                    },
                    raw_event_id=raw_event_id,
                    payload={
                        "duration_milliseconds": duration_milliseconds,
                        "operation": "webhook_ingestion",
                        "receipt_at": receipt_at.isoformat(),
                        "completion_at": completion_at.isoformat(),
                        "unit": "milliseconds",
                    },
                )
            )
            await observation_session.commit()
    except Exception:
        # This is deliberately logging-only: an observation failure must not
        # recurse into another system.error or affect the accepted webhook.
        logger.exception("Failed to record webhook ingestion latency: session={}", session_id)
