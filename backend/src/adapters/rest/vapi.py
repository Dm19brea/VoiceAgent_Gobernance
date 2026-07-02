from typing import Annotated

from fastapi import APIRouter, Depends
from loguru import logger
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.db.models import RawEvent
from src.infrastructure.db.session import get_session

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
    """Receive a Vapi webhook and persist it as a raw event (M1.6).

    Stores the whole Vapi body unmodified; ``event_type`` is Vapi's message
    type. Mapping to canonical governance events is deferred to M2. Always
    returns 200, as Vapi ignores any other status code.
    """
    event_type = webhook.message.type
    logger.info("Vapi webhook received: type={}", event_type)

    raw_event = RawEvent(event_type=event_type, payload=webhook.model_dump(mode="json"))
    session.add(raw_event)
    try:
        await session.commit()
    except Exception:
        logger.exception("Vapi webhook persistence failed: type={}", event_type)
        raise

    logger.info("Vapi webhook persisted: id={} type={}", raw_event.id, event_type)
    return {"status": "received"}
