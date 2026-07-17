"""CredentialsRepository: singleton get/create/bump_epoch (first-run-auth-setup)."""

import asyncio

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.infrastructure.config import settings
from src.infrastructure.repositories.credentials_repository import CredentialsRepository
from tests.fakes import FAKE_HASH


class TestCredentialsRepository:
    async def test_get_returns_none_when_empty(self, db_session: AsyncSession) -> None:
        repository = CredentialsRepository(db_session)

        assert await repository.get() is None

    async def test_create_inserts_singleton_row(self, db_session: AsyncSession) -> None:
        repository = CredentialsRepository(db_session)

        row = await repository.create(
            username="admin",
            password_hash=FAKE_HASH,
            jwt_secret="jwt-secret",
            vapi_webhook_secret="webhook-secret",
        )
        await db_session.commit()

        assert row.id == 1
        assert row.session_epoch == 0
        fetched = await repository.get()
        assert fetched is not None
        assert fetched.username == "admin"

    async def test_second_create_raises_conflict(self, db_session: AsyncSession) -> None:
        repository = CredentialsRepository(db_session)
        await repository.create(
            username="admin",
            password_hash=FAKE_HASH,
            jwt_secret="jwt-secret",
            vapi_webhook_secret="webhook-secret",
        )
        await db_session.commit()

        # ``create`` flushes, so the singleton PK/CHECK conflict raises here —
        # a single throwing invocation inside the ``pytest.raises`` block.
        with pytest.raises(IntegrityError):
            await repository.create(
                username="someone-else",
                password_hash=FAKE_HASH,
                jwt_secret="other-jwt-secret",
                vapi_webhook_secret="other-webhook-secret",
            )

    async def test_concurrent_create_persists_exactly_one_row(
        self, db_session: AsyncSession
    ) -> None:
        """Two racing setups resolve to a single row via the singleton constraint.

        Uses two independent sessions (the request fixture shares one session,
        which cannot model real concurrency) against the same test database.
        Exactly one insert commits; the loser fails with ``IntegrityError``.
        """
        engine = create_async_engine(settings.async_database_url)
        maker = async_sessionmaker(engine, expire_on_commit=False)

        async def attempt(username: str, jwt: str, webhook: str) -> None:
            async with maker() as session:
                await CredentialsRepository(session).create(
                    username=username,
                    password_hash=FAKE_HASH,
                    jwt_secret=jwt,
                    vapi_webhook_secret=webhook,
                )
                await session.commit()

        try:
            results = await asyncio.gather(
                attempt("first", "jwt-a", "webhook-a"),
                attempt("second", "jwt-b", "webhook-b"),
                return_exceptions=True,
            )
        finally:
            await engine.dispose()

        failures = [result for result in results if isinstance(result, BaseException)]
        assert len(failures) == 1
        assert isinstance(failures[0], IntegrityError)

        row = await CredentialsRepository(db_session).get()
        assert row is not None
        assert row.username in {"first", "second"}

    async def test_bump_epoch_increments(self, db_session: AsyncSession) -> None:
        repository = CredentialsRepository(db_session)
        await repository.create(
            username="admin",
            password_hash=FAKE_HASH,
            jwt_secret="jwt-secret",
            vapi_webhook_secret="webhook-secret",
        )
        await db_session.commit()

        await repository.bump_epoch()
        await db_session.commit()

        row = await repository.get()
        assert row is not None
        assert row.session_epoch == 1
