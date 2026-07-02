import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.db.base import Base


class RawEvent(Base):
    """Raw governance event as received at the REST boundary (M1 skeleton).

    Stores the unmodified event body in JSONB; ``event_type`` is lifted out so
    the trace can be queried without unpacking JSON. Superseded by the full
    Event entity in M2.
    """

    __tablename__ = "raw_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
