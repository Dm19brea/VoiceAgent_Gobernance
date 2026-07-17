"""SecretResolver: env override wins, else falls back to the DB row."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.secrets import SecretResolver
from src.infrastructure.config import settings
from src.infrastructure.repositories.credentials_repository import CredentialsRepository
from tests.fakes import FAKE_HASH


class TestSecretResolverPrecedence:
    async def test_env_override_wins_for_jwt_secret(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "jwt_secret", "env-jwt-secret")
        repository = CredentialsRepository(db_session)
        await repository.create(
            username="admin",
            password_hash=FAKE_HASH,
            jwt_secret="db-jwt-secret",
            vapi_webhook_secret="db-webhook-secret",
        )
        await db_session.commit()
        resolver = SecretResolver(repository)

        assert await resolver.jwt_secret() == "env-jwt-secret"

    async def test_db_value_used_when_no_env_jwt_secret(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "jwt_secret", "")
        repository = CredentialsRepository(db_session)
        await repository.create(
            username="admin",
            password_hash=FAKE_HASH,
            jwt_secret="db-jwt-secret",
            vapi_webhook_secret="db-webhook-secret",
        )
        await db_session.commit()
        resolver = SecretResolver(repository)

        assert await resolver.jwt_secret() == "db-jwt-secret"

    async def test_env_override_wins_for_webhook_secret(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "vapi_webhook_secret", "env-webhook-secret")
        repository = CredentialsRepository(db_session)
        await repository.create(
            username="admin",
            password_hash=FAKE_HASH,
            jwt_secret="db-jwt-secret",
            vapi_webhook_secret="db-webhook-secret",
        )
        await db_session.commit()
        resolver = SecretResolver(repository)

        assert await resolver.webhook_secret() == "env-webhook-secret"

    async def test_db_value_used_when_no_env_webhook_secret(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "vapi_webhook_secret", "")
        repository = CredentialsRepository(db_session)
        await repository.create(
            username="admin",
            password_hash=FAKE_HASH,
            jwt_secret="db-jwt-secret",
            vapi_webhook_secret="db-webhook-secret",
        )
        await db_session.commit()
        resolver = SecretResolver(repository)

        assert await resolver.webhook_secret() == "db-webhook-secret"

    async def test_jwt_secret_none_when_neither_env_nor_db(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "jwt_secret", "")
        repository = CredentialsRepository(db_session)
        resolver = SecretResolver(repository)

        assert await resolver.jwt_secret() is None

    async def test_webhook_secret_none_when_neither_env_nor_db(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "vapi_webhook_secret", "")
        repository = CredentialsRepository(db_session)
        resolver = SecretResolver(repository)

        assert await resolver.webhook_secret() is None
