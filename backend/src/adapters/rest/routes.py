from fastapi import APIRouter

from src.adapters.rest.schemas import EventIn

router = APIRouter()


@router.post("/events", status_code=202)
def ingest_event(event: EventIn) -> EventIn:
    """Ingest a governance event.

    M1.2: validate against the EventIn contract (FastAPI returns 422 on
    invalid input) and echo it back. Persistence is wired in M1.4.
    """
    return event
