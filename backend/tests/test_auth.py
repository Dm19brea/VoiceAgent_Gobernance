"""S2 — JWT dashboard authentication: login, token roundtrip, route guard."""

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
import pytest
from httpx import AsyncClient

from src.adapters.rest.auth import issue_token, require_auth, verify_token
from src.infrastructure.config import settings
from src.main import app


def _set_credentials(monkeypatch: pytest.MonkeyPatch, username: str, password: str) -> None:
    monkeypatch.setattr(settings, "dashboard_username", username)
    monkeypatch.setattr(
        settings,
        "dashboard_password_hash",
        bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8"),
    )
    monkeypatch.setattr(settings, "jwt_secret", "test-jwt-secret")


class TestTokenRoundtrip:
    def test_issue_then_verify_returns_subject(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "jwt_secret", "test-jwt-secret")

        token = issue_token("admin")

        assert verify_token(token) == "admin"

    def test_verify_rejects_expired_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "jwt_secret", "test-jwt-secret")
        now = datetime.now(UTC)
        expired = jwt.encode(
            {"sub": "admin", "iat": now - timedelta(hours=13), "exp": now - timedelta(hours=1)},
            settings.jwt_secret,
            algorithm="HS256",
        )

        with pytest.raises(jwt.PyJWTError):
            verify_token(expired)

    def test_verify_rejects_bad_signature(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "jwt_secret", "test-jwt-secret")
        now = datetime.now(UTC)
        forged = jwt.encode(
            {"sub": "admin", "iat": now, "exp": now + timedelta(hours=1)},
            "some-other-secret",
            algorithm="HS256",
        )

        with pytest.raises(jwt.PyJWTError):
            verify_token(forged)


class TestLoginEndpoint:
    async def test_correct_credentials_issue_token(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_credentials(monkeypatch, "admin", "correct-horse")

        response = await client.post(
            "/auth/login", json={"username": "admin", "password": "correct-horse"}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["token_type"] == "bearer"
        assert verify_token(body["access_token"]) == "admin"

    async def test_wrong_password_rejected(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_credentials(monkeypatch, "admin", "correct-horse")

        response = await client.post(
            "/auth/login", json={"username": "admin", "password": "wrong"}
        )

        assert response.status_code == 401

    async def test_wrong_username_rejected(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_credentials(monkeypatch, "admin", "correct-horse")

        response = await client.post(
            "/auth/login", json={"username": "someone-else", "password": "correct-horse"}
        )

        assert response.status_code == 401

    async def test_unconfigured_password_hash_rejects_instead_of_500(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "dashboard_username", "admin")
        monkeypatch.setattr(settings, "dashboard_password_hash", "")

        response = await client.post(
            "/auth/login", json={"username": "admin", "password": "anything"}
        )

        assert response.status_code == 401


class TestRouteGuard:
    async def test_anonymous_request_rejected(self, client: AsyncClient) -> None:
        app.dependency_overrides.pop(require_auth, None)

        response = await client.get("/agents")

        assert response.status_code == 401

    async def test_valid_token_allows_request(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_credentials(monkeypatch, "admin", "correct-horse")
        app.dependency_overrides.pop(require_auth, None)

        login_response = await client.post(
            "/auth/login", json={"username": "admin", "password": "correct-horse"}
        )
        token = login_response.json()["access_token"]

        response = await client.get("/agents", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 200

    async def test_invalid_token_rejected(self, client: AsyncClient) -> None:
        app.dependency_overrides.pop(require_auth, None)

        response = await client.get(
            "/agents", headers={"Authorization": "Bearer not-a-real-token"}
        )

        assert response.status_code == 401
