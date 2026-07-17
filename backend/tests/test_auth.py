"""First-run setup + session lifecycle: status, setup, login, refresh, logout."""

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.rest.auth import (
    ACCESS_TOKEN_TTL,
    JWT_ALGORITHM,
    require_auth,
)
from src.infrastructure.config import settings
from src.infrastructure.repositories.credentials_repository import CredentialsRepository
from src.main import app
from tests.fakes import FAKE_LOGIN

# Fictitious login values used only by these tests — not real credentials.
_VALID_PASSWORD = FAKE_LOGIN
_USERNAME = "admin"


async def _seed_credentials(
    db_session: AsyncSession,
    *,
    username: str = _USERNAME,
    password: str = _VALID_PASSWORD,
    jwt_secret: str = "test-jwt-secret",
    webhook_secret: str = "test-webhook-secret",
) -> None:
    repository = CredentialsRepository(db_session)
    await repository.create(
        username=username,
        password_hash=bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8"),
        jwt_secret=jwt_secret,
        vapi_webhook_secret=webhook_secret,
    )
    await db_session.commit()


@pytest.fixture(autouse=True)
def _env_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the env-override JWT secret stable across this module's tests."""
    monkeypatch.setattr(settings, "jwt_secret", "test-jwt-secret")


class TestAuthStatus:
    async def test_needs_setup_true_when_unconfigured(self, client: AsyncClient) -> None:
        response = await client.get("/auth/status")

        assert response.status_code == 200
        assert response.json() == {"needs_setup": True}

    async def test_needs_setup_false_when_configured(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_credentials(db_session)

        response = await client.get("/auth/status")

        assert response.status_code == 200
        assert response.json() == {"needs_setup": False}


class TestAuthSetup:
    async def test_first_successful_setup_persists_row_and_issues_session(
        self, client: AsyncClient
    ) -> None:
        response = await client.post(
            "/auth/setup", json={"username": _USERNAME, "password": _VALID_PASSWORD}
        )

        assert response.status_code == 200
        body = response.json()
        assert "access_token" in body
        assert "vapi_webhook_secret" in body
        assert response.cookies.get("refresh_token") is not None

        status_response = await client.get("/auth/status")
        assert status_response.json() == {"needs_setup": False}

    async def test_setup_rejected_when_already_configured(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_credentials(db_session)

        response = await client.post(
            "/auth/setup", json={"username": "someone-else", "password": _VALID_PASSWORD}
        )

        assert response.status_code == 409

    async def test_weak_password_rejected_with_all_unmet_rules(self, client: AsyncClient) -> None:
        response = await client.post(
            "/auth/setup", json={"username": _USERNAME, "password": "weakpassword"}
        )

        assert response.status_code == 422
        violations = response.json()["detail"]
        assert "uppercase" in violations
        assert "digit" in violations
        assert "special" in violations

        status_response = await client.get("/auth/status")
        assert status_response.json() == {"needs_setup": True}


class TestAuthLogin:
    async def test_successful_login_issues_access_and_refresh(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_credentials(db_session)

        response = await client.post(
            "/auth/login", json={"username": _USERNAME, "password": _VALID_PASSWORD}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["token_type"] == "bearer"
        assert "access_token" in body
        assert response.cookies.get("refresh_token") is not None

    async def test_wrong_password_rejected(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_credentials(db_session)

        response = await client.post(
            "/auth/login", json={"username": _USERNAME, "password": "wrong-password"}
        )

        assert response.status_code == 401

    async def test_wrong_username_rejected(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_credentials(db_session)

        response = await client.post(
            "/auth/login", json={"username": "someone-else", "password": _VALID_PASSWORD}
        )

        assert response.status_code == 401

    async def test_login_rejected_when_unconfigured(self, client: AsyncClient) -> None:
        response = await client.post(
            "/auth/login", json={"username": _USERNAME, "password": _VALID_PASSWORD}
        )

        assert response.status_code == 401


class TestAuthRefresh:
    async def test_refresh_within_both_windows_issues_new_access_token(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_credentials(db_session)
        await client.post("/auth/login", json={"username": _USERNAME, "password": _VALID_PASSWORD})

        response = await client.post("/auth/refresh")

        assert response.status_code == 200
        assert "access_token" in response.json()
        assert response.cookies.get("refresh_token") is not None

    async def test_refresh_past_inactivity_window_rejected(
        self, client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await _seed_credentials(db_session)
        now = datetime.now(UTC)
        stale_refresh = jwt.encode(
            {
                "sub": _USERNAME,
                "type": "refresh",
                "iat": now - timedelta(minutes=31),
                "exp": now - timedelta(minutes=1),
                "abs_exp": (now + timedelta(hours=7)).timestamp(),
                "epoch": 0,
            },
            "test-jwt-secret",
            algorithm=JWT_ALGORITHM,
        )
        client.cookies.set("refresh_token", stale_refresh)

        response = await client.post("/auth/refresh")

        assert response.status_code == 401

    async def test_refresh_past_absolute_cap_rejected(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_credentials(db_session)
        now = datetime.now(UTC)
        expired_absolute = jwt.encode(
            {
                "sub": _USERNAME,
                "type": "refresh",
                "iat": now,
                "exp": (now + timedelta(minutes=30)).timestamp(),
                "abs_exp": (now - timedelta(hours=1)).timestamp(),
                "epoch": 0,
            },
            "test-jwt-secret",
            algorithm=JWT_ALGORITHM,
        )
        client.cookies.set("refresh_token", expired_absolute)

        response = await client.post("/auth/refresh")

        assert response.status_code == 401

    async def test_missing_cookie_rejected(self, client: AsyncClient) -> None:
        response = await client.post("/auth/refresh")

        assert response.status_code == 401

    async def test_new_refresh_token_never_extends_past_absolute_cap(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_credentials(db_session)
        now = datetime.now(UTC)
        abs_exp = (now + timedelta(minutes=5)).timestamp()
        near_cap_refresh = jwt.encode(
            {
                "sub": _USERNAME,
                "type": "refresh",
                "iat": now,
                "exp": (now + timedelta(minutes=30)).timestamp(),
                "abs_exp": abs_exp,
                "epoch": 0,
            },
            "test-jwt-secret",
            algorithm=JWT_ALGORITHM,
        )
        client.cookies.set("refresh_token", near_cap_refresh)

        response = await client.post("/auth/refresh")

        assert response.status_code == 200
        new_refresh = response.cookies.get("refresh_token")
        assert new_refresh is not None
        decoded = jwt.decode(
            new_refresh,
            "test-jwt-secret",
            algorithms=[JWT_ALGORITHM],
            options={"verify_exp": False},
        )
        assert decoded["abs_exp"] == abs_exp


class TestAuthLogout:
    async def test_logout_revokes_prior_tokens(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_credentials(db_session)
        login_response = await client.post(
            "/auth/login", json={"username": _USERNAME, "password": _VALID_PASSWORD}
        )
        old_access_token = login_response.json()["access_token"]

        logout_response = await client.post("/auth/logout")
        assert logout_response.status_code == 200
        assert logout_response.cookies.get("refresh_token") is None

        app.dependency_overrides.pop(require_auth, None)
        protected_response = await client.get(
            "/agents", headers={"Authorization": f"Bearer {old_access_token}"}
        )

        assert protected_response.status_code == 401

    async def test_refresh_rejected_after_logout(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_credentials(db_session)
        await client.post("/auth/login", json={"username": _USERNAME, "password": _VALID_PASSWORD})

        await client.post("/auth/logout")
        response = await client.post("/auth/refresh")

        assert response.status_code == 401


class TestRouteGuard:
    async def test_anonymous_request_rejected(self, client: AsyncClient) -> None:
        app.dependency_overrides.pop(require_auth, None)

        response = await client.get("/agents")

        assert response.status_code == 401

    async def test_valid_token_allows_request(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_credentials(db_session)
        app.dependency_overrides.pop(require_auth, None)

        login_response = await client.post(
            "/auth/login", json={"username": _USERNAME, "password": _VALID_PASSWORD}
        )
        token = login_response.json()["access_token"]

        response = await client.get("/agents", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 200

    async def test_invalid_token_rejected(self, client: AsyncClient) -> None:
        app.dependency_overrides.pop(require_auth, None)

        response = await client.get("/agents", headers={"Authorization": "Bearer not-a-real-token"})

        assert response.status_code == 401


class TestTokenEpoch:
    async def test_access_token_carries_current_epoch(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_credentials(db_session)

        login_response = await client.post(
            "/auth/login", json={"username": _USERNAME, "password": _VALID_PASSWORD}
        )
        token = login_response.json()["access_token"]
        decoded = jwt.decode(token, "test-jwt-secret", algorithms=[JWT_ALGORITHM])

        assert decoded["epoch"] == 0
        assert decoded["type"] == "access"

    def test_access_token_expiry_matches_fifteen_minutes(self) -> None:
        assert timedelta(minutes=15) == ACCESS_TOKEN_TTL
