from typing import Annotated

from fastapi import APIRouter, Depends
from loguru import logger
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.rest.vapi_mapping import map_vapi_event
from src.application.use_cases.ingest_event import IngestEvent
from src.domain.enums import EventType
from src.infrastructure.celery.tasks import build_session_evidences
from src.infrastructure.db.models import RawEvent
from src.infrastructure.db.session import get_session
from src.infrastructure.repositories.governance_repository import SqlAlchemyGovernanceRepository

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


class VapiMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str


class VapiWebhook(BaseModel):
    """Vapi server-message envelope. Unknown fields are kept (extra=allow)."""

    model_config = ConfigDict(extra="allow")

    message: VapiMessage


@router.post("/webhooks/vapi", status_code=200)
async def vapi_webhook(webhook: VapiWebhook, session: SessionDep) -> dict[str, str]:
    """Receive a Vapi webhook, land it raw, and promote it to the domain (M2.7).

    The raw body is always stored in ``raw_events`` (immutable landing). If the
    Vapi type maps to a canonical event, it is also ingested into the
    Session/Event trace. Always returns 200, as Vapi ignores other status codes.
    """
    event_type = webhook.message.type
    raw = webhook.model_dump(mode="json")
    logger.info("Vapi webhook received: type={}", event_type)

    session.add(RawEvent(event_type=event_type, payload=raw))

    command = map_vapi_event(raw)
    if command is not None:
        repository = SqlAlchemyGovernanceRepository(session)
        await IngestEvent(repository).execute(command)

    try:
        await session.commit()
    except Exception:
        logger.exception("Vapi webhook persistence failed: type={}", event_type)
        raise

    # Session closed: build its evidences asynchronously (does not block the response).
    # A broker failure must not break ingestion, so the enqueue is best-effort.
    if command is not None and command.event_type is EventType.SESSION_ENDED:
        try:
            build_session_evidences.delay(command.call_id)
        except Exception:
            logger.exception("Failed to enqueue evidence build: session={}", command.call_id)

    logger.info("Vapi webhook persisted: type={}", event_type)
    return {"status": "received"}
