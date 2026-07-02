from typing import Annotated

from fastapi import APIRouter, Depends
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
    input) and persists the raw event body in ``raw_events`` (M1.4).
    """
    raw_event = RawEvent(
        event_type=event.event_type,
        payload=event.model_dump(mode="json"),
    )
    session.add(raw_event)
    await session.commit()
    return event
