from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.db.models import AppCredentials


class CredentialsRepository:
    """Singleton ``app_credentials`` access: get / create / bump_epoch.

    Read per request, uncached (design decision Q4): a singleton PK lookup is
    sub-ms and caching would create cross-replica staleness across multiple
    Railway instances.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self) -> AppCredentials | None:
        return await self._session.get(AppCredentials, 1)

    async def create(
        self,
        *,
        username: str,
        password_hash: str,
        jwt_secret: str,
        vapi_webhook_secret: str,
    ) -> AppCredentials:
        """Insert the singleton row. Raises ``IntegrityError`` if one already exists.

        Callers running concurrent setup attempts rely on the primary-key
        conflict (or the ``id = 1`` CHECK) to make exactly one insert win.
        """
        row = AppCredentials(
            id=1,
            username=username,
            password_hash=password_hash,
            jwt_secret=jwt_secret,
            vapi_webhook_secret=vapi_webhook_secret,
            session_epoch=0,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def bump_epoch(self) -> None:
        """Increment ``session_epoch``, globally revoking all prior tokens."""
        await self._session.execute(
            update(AppCredentials)
            .where(AppCredentials.id == 1)
            .values(session_epoch=AppCredentials.session_epoch + 1)
        )
        await self._session.flush()
