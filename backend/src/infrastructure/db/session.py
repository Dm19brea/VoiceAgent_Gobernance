from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.infrastructure.config import settings

engine = create_async_engine(settings.async_database_url, echo=False)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an async DB session."""
    async with async_session_maker() as session:
        yield session
