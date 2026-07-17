"""CredentialsRepository: singleton get/create/bump_epoch (first-run-auth-setup)."""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.repositories.credentials_repository import CredentialsRepository


class TestCredentialsRepository:
    async def test_get_returns_none_when_empty(self, db_session: AsyncSession) -> None:
        repository = CredentialsRepository(db_session)

        assert await repository.get() is None

    async def test_create_inserts_singleton_row(self, db_session: AsyncSession) -> None:
        repository = CredentialsRepository(db_session)

        row = await repository.create(
            username="admin",
            password_hash="hashed",
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
            password_hash="hashed",
            jwt_secret="jwt-secret",
            vapi_webhook_secret="webhook-secret",
        )
        await db_session.commit()

        with pytest.raises(IntegrityError):
            await repository.create(
                username="someone-else",
                password_hash="other-hash",
                jwt_secret="other-jwt-secret",
                vapi_webhook_secret="other-webhook-secret",
            )
            await db_session.commit()

    async def test_bump_epoch_increments(self, db_session: AsyncSession) -> None:
        repository = CredentialsRepository(db_session)
        await repository.create(
            username="admin",
            password_hash="hashed",
            jwt_secret="jwt-secret",
            vapi_webhook_secret="webhook-secret",
        )
        await db_session.commit()

        await repository.bump_epoch()
        await db_session.commit()

        row = await repository.get()
        assert row is not None
        assert row.session_epoch == 1
