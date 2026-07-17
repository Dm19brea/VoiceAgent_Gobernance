"""First-run setup + session lifecycle: status, setup, login, refresh, logout.

Dashboard credentials and the app-owned secrets (`jwt_secret`,
`vapi_webhook_secret`) live in the singleton ``app_credentials`` DB row,
provisioned once via ``/auth/setup``. Access tokens are short-lived (15 min);
the refresh token is an HttpOnly cookie carrying both a sliding inactivity
window (30 min) and an absolute cap (login + 8h). ``session_epoch`` allows
global revocation (logout) without a per-jti blocklist: every issued token
embeds the epoch active at issue time, and verification rejects tokens whose
epoch no longer matches the DB row.
"""

import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

import bcrypt
import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.password_policy import validate as validate_password
from src.domain.secrets import SecretResolver
from src.infrastructure.config import settings
from src.infrastructure.db.session import get_session
from src.infrastructure.repositories.credentials_repository import CredentialsRepository

router = APIRouter(tags=["auth"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TTL = timedelta(minutes=15)
REFRESH_SLIDING_TTL = timedelta(minutes=30)
REFRESH_ABSOLUTE_TTL = timedelta(hours=8)

REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_PATH = "/auth"

TokenType = Literal["access", "refresh"]


class StatusOut(BaseModel):
    needs_setup: bool


class SetupIn(BaseModel):
    username: str
    password: str


class LoginIn(BaseModel):
    username: str
    password: str


class SessionOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class SetupOut(SessionOut):
    vapi_webhook_secret: str


def _cookie_flags(request: Request) -> dict[str, Any]:
    """Derive Secure/SameSite per-request from the scheme (design Q1).

    Cross-site deployments (Railway front/back on distinct `*.up.railway.app`
    origins) are served over https and need `SameSite=None; Secure`; a local
    same-site `http://localhost` setup works with `SameSite=Lax` and no
    `Secure` flag (browsers reject `Secure` cookies without https).
    `AUTH_COOKIE_SECURE` overrides the scheme-derived default for edge
    proxies that terminate TLS before `request.url.scheme` reflects it.
    """
    override = getattr(settings, "auth_cookie_secure", None)
    is_secure = override if override is not None else request.url.scheme == "https"
    same_site = "none" if is_secure else "lax"
    return {"secure": is_secure, "samesite": same_site}


def _set_refresh_cookie(response: Response, request: Request, token: str) -> None:
    flags = _cookie_flags(request)
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        token,
        httponly=True,
        path=REFRESH_COOKIE_PATH,
        secure=flags["secure"],
        samesite=flags["samesite"],
    )


def _clear_refresh_cookie(response: Response, request: Request) -> None:
    flags = _cookie_flags(request)
    response.delete_cookie(
        REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
        secure=flags["secure"],
        samesite=flags["samesite"],
    )


def _issue_access_token(username: str, epoch: int, secret: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": username,
        "type": "access",
        "iat": now,
        "exp": now + ACCESS_TOKEN_TTL,
        "epoch": epoch,
    }
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


def _issue_refresh_token(
    username: str, epoch: int, secret: str, *, abs_exp: float | None = None
) -> str:
    """Issue a refresh token. Rotates on every refresh (design Q3).

    A fresh ``iat``/sliding ``exp`` is always minted; ``abs_exp`` is preserved
    from the original login unless this IS that original issuance.
    """
    now = datetime.now(UTC)
    resolved_abs_exp = abs_exp if abs_exp is not None else (now + REFRESH_ABSOLUTE_TTL).timestamp()
    payload = {
        "sub": username,
        "type": "refresh",
        "iat": now,
        "exp": now + REFRESH_SLIDING_TTL,
        "abs_exp": resolved_abs_exp,
        "epoch": epoch,
    }
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


def _decode_token(token: str, secret: str, expected_type: TokenType) -> dict[str, Any]:
    """Decode and validate a token's type, signature, and standard `exp`.

    Raises ``jwt.PyJWTError`` on any invalid/expired/malformed/wrong-type
    token — callers translate that into the appropriate rejection.
    """
    payload = jwt.decode(token, secret, algorithms=[JWT_ALGORITHM])
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(f"expected token type {expected_type!r}")
    return payload


def _resolver(session: AsyncSession) -> SecretResolver:
    return SecretResolver(CredentialsRepository(session))


@router.get("/auth/status", summary="First-run detection")
async def auth_status(session: SessionDep) -> StatusOut:
    row = await CredentialsRepository(session).get()
    return StatusOut(needs_setup=row is None)


@router.post(
    "/auth/setup",
    summary="First-run credential provisioning",
    responses={409: {"description": "Already configured"}, 422: {"description": "Weak password"}},
)
async def setup(
    body: SetupIn, request: Request, response: Response, session: SessionDep
) -> SetupOut:
    repository = CredentialsRepository(session)
    if await repository.get() is not None:
        raise HTTPException(status_code=409, detail="Already configured")

    violations = validate_password(body.password)
    if violations:
        raise HTTPException(status_code=422, detail=violations)

    password_hash = bcrypt.hashpw(body.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    jwt_secret = secrets.token_urlsafe(48)
    webhook_secret = secrets.token_urlsafe(32)

    try:
        row = await repository.create(
            username=body.username,
            password_hash=password_hash,
            jwt_secret=jwt_secret,
            vapi_webhook_secret=webhook_secret,
        )
        await session.commit()
    except Exception as exc:
        await session.rollback()
        # Concurrent setup: exactly one insert wins (PK/CHECK conflict).
        raise HTTPException(status_code=409, detail="Already configured") from exc

    resolver = _resolver(session)
    effective_secret = await resolver.jwt_secret() or jwt_secret
    access_token = _issue_access_token(row.username, row.session_epoch, effective_secret)
    refresh_token = _issue_refresh_token(row.username, row.session_epoch, effective_secret)
    _set_refresh_cookie(response, request, refresh_token)

    return SetupOut(access_token=access_token, vapi_webhook_secret=webhook_secret)


@router.post(
    "/auth/login",
    summary="Dashboard login",
    responses={401: {"description": "Invalid credentials"}},
)
async def login(
    body: LoginIn, request: Request, response: Response, session: SessionDep
) -> SessionOut:
    repository = CredentialsRepository(session)
    row = await repository.get()
    if row is None or row.username != body.username:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    try:
        valid = bcrypt.checkpw(body.password.encode("utf-8"), row.password_hash.encode("utf-8"))
    except ValueError:
        valid = False
    if not valid:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    resolver = _resolver(session)
    secret = await resolver.jwt_secret() or row.jwt_secret
    access_token = _issue_access_token(row.username, row.session_epoch, secret)
    refresh_token = _issue_refresh_token(row.username, row.session_epoch, secret)
    _set_refresh_cookie(response, request, refresh_token)

    return SessionOut(access_token=access_token)


@router.post(
    "/auth/refresh",
    summary="Silent token refresh",
    responses={401: {"description": "Session expired"}},
)
async def refresh(request: Request, response: Response, session: SessionDep) -> SessionOut:
    raw_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if raw_token is None:
        raise HTTPException(status_code=401, detail="Missing refresh cookie")

    repository = CredentialsRepository(session)
    row = await repository.get()
    if row is None:
        raise HTTPException(status_code=401, detail="Not configured")

    resolver = _resolver(session)
    secret = await resolver.jwt_secret() or row.jwt_secret

    try:
        payload = _decode_token(raw_token, secret, "refresh")
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired session") from exc

    if payload.get("epoch") != row.session_epoch:
        raise HTTPException(status_code=401, detail="Session revoked")

    abs_exp = payload.get("abs_exp")
    if abs_exp is None or abs_exp <= datetime.now(UTC).timestamp():
        raise HTTPException(status_code=401, detail="Session expired")

    username = payload["sub"]
    new_access_token = _issue_access_token(username, row.session_epoch, secret)
    new_refresh_token = _issue_refresh_token(username, row.session_epoch, secret, abs_exp=abs_exp)
    _set_refresh_cookie(response, request, new_refresh_token)

    return SessionOut(access_token=new_access_token)


@router.post("/auth/logout", summary="Revoke the current session")
async def logout(request: Request, response: Response, session: SessionDep) -> dict[str, str]:
    repository = CredentialsRepository(session)
    if await repository.get() is not None:
        await repository.bump_epoch()
        await session.commit()
    _clear_refresh_cookie(response, request)
    return {"status": "logged_out"}


async def verify_access_token(token: str, session: AsyncSession) -> str:
    """Verify a DB-backed access token shared by REST and WebSocket auth.

    Resolves the signing secret (env override else the credentials row),
    decodes the token as an ``access`` token, and checks its embedded
    ``epoch`` against the current ``session_epoch``. Raises
    ``jwt.InvalidTokenError`` on any failure: no credentials row, decode
    error, wrong token type, or revoked (epoch-mismatched) token.
    """
    repository = CredentialsRepository(session)
    row = await repository.get()
    if row is None:
        raise jwt.InvalidTokenError("Not configured")

    resolver = _resolver(session)
    secret = await resolver.jwt_secret() or row.jwt_secret

    payload = _decode_token(token, secret, "access")

    if payload.get("epoch") != row.session_epoch:
        raise jwt.InvalidTokenError("Session revoked")

    subject: str = payload["sub"]
    return subject


async def require_auth(
    session: SessionDep, authorization: str | None = Header(default=None)
) -> str:
    """FastAPI dependency guarding protected REST routes.

    Overridden in tests via ``app.dependency_overrides[require_auth]``.
    """
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization.removeprefix("Bearer ")

    try:
        return await verify_access_token(token, session)
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc
