from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.infrastructure.config import settings
from src.infrastructure.db.base import Base
from src.infrastructure.db.models import (
    AgentModel,
    EventModel,
    EvidenceModel,
    RawEvent,
    SessionModel,
)
from src.infrastructure.db.session import get_session
from src.main import app


async def _clean(conn: AsyncConnection) -> None:
    # FK order: evidences/events -> sessions -> agents; raw_events is independent.
    await conn.execute(delete(EvidenceModel))
    await conn.execute(delete(EventModel))
    await conn.execute(delete(SessionModel))
    await conn.execute(delete(AgentModel))
    await conn.execute(delete(RawEvent))


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Async session against the test database, with a clean schema per test."""
    engine = create_async_engine(settings.async_database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _clean(conn)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session

    async with engine.begin() as conn:
        await _clean(conn)
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """HTTP client whose requests use the test DB session."""

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
