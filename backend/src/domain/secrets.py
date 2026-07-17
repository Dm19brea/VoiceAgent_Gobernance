"""Env-override-else-DB secret resolution for jwt_secret and vapi_webhook_secret.

Dashboard username/password stay DB-only (no env fallback, design Option A);
this resolver only applies to the two app-owned secrets that historically
lived in ``.env`` and now default to being auto-provisioned into the
``app_credentials`` singleton row at first-run setup.
"""

from src.infrastructure.config import settings
from src.infrastructure.repositories.credentials_repository import CredentialsRepository


class SecretResolver:
    """Resolves a secret from an explicit env override, else the DB row."""

    def __init__(self, repository: CredentialsRepository) -> None:
        self._repository = repository

    async def jwt_secret(self) -> str | None:
        if settings.jwt_secret:
            return settings.jwt_secret
        row = await self._repository.get()
        return row.jwt_secret if row is not None else None

    async def webhook_secret(self) -> str | None:
        if settings.vapi_webhook_secret:
            return settings.vapi_webhook_secret
        row = await self._repository.get()
        return row.vapi_webhook_secret if row is not None else None
