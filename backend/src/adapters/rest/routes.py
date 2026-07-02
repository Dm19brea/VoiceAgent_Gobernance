from typing import Annotated

from fastapi import APIRouter, Depends
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.rest.schemas import EventIn
from src.infrastructure.db.models import RawEvent
from src.infrastructure.db.session import get_session

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post("/events", status_code=202)
async def ingest_event(event: EventIn, session: SessionDep) -> EventIn:
    """Ingest a governance event.

    Validates against the EventIn contract (FastAPI returns 422 on invalid
    input), persists the raw event body in ``raw_events`` and traces the
    lifecycle with Loguru (M1.5).
    """
    logger.info("Event received: type={} agent={}", event.event_type, event.agent_id)

    raw_event = RawEvent(
        event_type=event.event_type,
        payload=event.model_dump(mode="json"),
    )
    session.add(raw_event)
    try:
        await session.commit()
    except Exception:
        logger.exception("Event persistence failed: type={}", event.event_type)
        raise

    logger.info("Event persisted: id={} type={}", raw_event.id, event.event_type)
    return event
