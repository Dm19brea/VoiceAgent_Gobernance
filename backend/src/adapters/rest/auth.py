"""S2 — JWT dashboard authentication.

Single-tenant login: one username/password pair sourced from Settings
(``DASHBOARD_USERNAME`` + bcrypt ``DASHBOARD_PASSWORD_HASH``) issues a 12h
JWT with no refresh. ``require_auth`` is a FastAPI dependency guarding the
protected REST routers; it is overridable via ``app.dependency_overrides``
in tests, mirroring the existing ``get_assistant_directory`` seam.
"""

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from src.infrastructure.config import settings

router = APIRouter(tags=["auth"])

JWT_ALGORITHM = "HS256"
TOKEN_TTL = timedelta(hours=12)


class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


def issue_token(username: str) -> str:
    """Issue a 12h JWT for the given subject. No refresh token is issued."""
    now = datetime.now(UTC)
    payload = {"sub": username, "iat": now, "exp": now + TOKEN_TTL}
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> str:
    """Decode and validate a JWT, returning its subject.

    Raises ``jwt.PyJWTError`` (or a subclass, e.g. ``ExpiredSignatureError``,
    ``InvalidSignatureError``) on any invalid/expired/malformed token —
    callers translate that into the appropriate rejection.
    """
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGORITHM])
    subject: str = payload["sub"]
    return subject


def _credentials_valid(username: str, password: str) -> bool:
    if username != settings.dashboard_username:
        return False
    if not settings.dashboard_password_hash:
        # Unconfigured hash must fail closed, not raise a bcrypt ValueError.
        return False
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"), settings.dashboard_password_hash.encode("utf-8")
        )
    except ValueError:
        return False


@router.post(
    "/auth/login",
    summary="Dashboard login",
    responses={401: {"description": "Invalid credentials"}},
)
def login(body: LoginIn) -> TokenOut:
    if not _credentials_valid(body.username, body.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return TokenOut(access_token=issue_token(body.username))


def require_auth(authorization: str | None = Header(default=None)) -> str:
    """FastAPI dependency guarding protected REST routes.

    Overridden in tests via ``app.dependency_overrides[require_auth]``.
    """
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization.removeprefix("Bearer ")
    try:
        return verify_token(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc
