"""Remote access authentication middleware."""

from __future__ import annotations

import os
import secrets
import string
import time
from collections.abc import Awaitable, Callable, Iterable

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware

from backend.modules.auth.utils import validate_session


AUTH_COOKIE_NAME = "CountBot_token"
SETUP_SECRET_HEADER_NAME = "x-setup-secret"
SETUP_SECRET_LENGTH = 8
SETUP_SECRET_ALPHABET = string.ascii_letters
SETUP_SECRET_TTL_MINUTES_ENV = "REMOTE_SETUP_SECRET_TTL_MINUTES"
SETUP_SECRET_TTL_MINUTES_MIN = 10
SETUP_SECRET_TTL_MINUTES_MAX = 120
SETUP_SECRET_TTL_MINUTES_DEFAULT = 30

_FORWARDED_HEADER_NAMES = {
    "x-forwarded-for",
    "x-real-ip",
    "forwarded",
}

_PUBLIC_PATH_PREFIXES = (
    "/api/auth/",
    "/api/health",
    "/api/system/health",
)

_PROTECTED_PATH_PREFIXES = (
    "/api/",
)

_LOCAL_ONLY_SETUP_PATHS = (
    "/api/auth/setup",
)


def get_remote_setup_secret(app) -> str:
    return getattr(app.state, "remote_setup_secret", "")


def get_remote_setup_secret_expires_at(app) -> float:
    return float(getattr(app.state, "remote_setup_secret_expires_at", 0.0) or 0.0)


def get_remote_setup_secret_ttl_minutes() -> int:
    raw_value = os.getenv(SETUP_SECRET_TTL_MINUTES_ENV, str(SETUP_SECRET_TTL_MINUTES_DEFAULT)).strip()
    try:
        ttl_minutes = int(raw_value)
    except ValueError:
        ttl_minutes = SETUP_SECRET_TTL_MINUTES_DEFAULT
    return max(SETUP_SECRET_TTL_MINUTES_MIN, min(SETUP_SECRET_TTL_MINUTES_MAX, ttl_minutes))


def is_remote_setup_secret_expired(app) -> bool:
    expires_at = get_remote_setup_secret_expires_at(app)
    return expires_at > 0 and time.time() >= expires_at


def ensure_remote_setup_secret(app) -> str:
    secret = get_remote_setup_secret(app)
    had_secret = bool(secret)
    expired = had_secret and is_remote_setup_secret_expired(app)
    if not secret or expired:
        secret = "".join(secrets.choice(SETUP_SECRET_ALPHABET) for _ in range(SETUP_SECRET_LENGTH))
        app.state.remote_setup_secret = secret
        app.state.remote_setup_secret_expires_at = time.time() + get_remote_setup_secret_ttl_minutes() * 60
        if expired:
            logger.info(
                f"Remote setup secret expired and was refreshed for another {get_remote_setup_secret_ttl_minutes()} minute(s): /setup/{secret}"
            )
    return secret


def clear_remote_setup_secret(app) -> None:
    app.state.remote_setup_secret = ""
    app.state.remote_setup_secret_expires_at = 0.0


def has_valid_remote_setup_secret(app, candidate: str | None) -> bool:
    if is_remote_setup_secret_expired(app):
        ensure_remote_setup_secret(app)
        return False
    secret = get_remote_setup_secret(app)
    provided = (candidate or "").strip()
    return bool(secret and provided and secrets.compare_digest(secret, provided))


def request_has_valid_remote_setup_secret(request: Request) -> bool:
    return has_valid_remote_setup_secret(
        request.app,
        request.headers.get(SETUP_SECRET_HEADER_NAME, ""),
    )


def _is_loopback_host(host: str | None) -> bool:
    if not host:
        return False
    normalized = host.strip().lower()
    return normalized in {"127.0.0.1", "::1", "localhost"}


def is_direct_local_client(client_ip: str | None, header_keys: Iterable[str]) -> bool:
    """Return True only for direct loopback requests without proxy headers."""
    if not _is_loopback_host(client_ip):
        return False

    normalized_headers = {key.lower() for key in header_keys}
    return not any(header in normalized_headers for header in _FORWARDED_HEADER_NAMES)


def _is_local_request(request: Request) -> bool:
    client_ip = request.client.host if request.client and request.client.host else None
    return is_direct_local_client(client_ip, request.headers.keys())


class RemoteAuthMiddleware(BaseHTTPMiddleware):
    """Protect non-local HTTP requests with cookie or bearer-token auth."""

    def __init__(
        self,
        app,
        get_password_hash_fn: Callable[[], Awaitable[str]],
    ) -> None:
        super().__init__(app)
        self._get_password_hash = get_password_hash_fn

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        if _is_local_request(request):
            return await call_next(request)

        if not any(path.startswith(prefix) for prefix in _PROTECTED_PATH_PREFIXES):
            return await call_next(request)

        if any(path.startswith(prefix) for prefix in _PUBLIC_PATH_PREFIXES):
            if (
                path in _LOCAL_ONLY_SETUP_PATHS
                and not _is_local_request(request)
                and not request_has_valid_remote_setup_secret(request)
            ):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "首次初始化只能在本机完成", "code": "SETUP_LOCAL_ONLY"},
                )
            return await call_next(request)

        password_hash = await self._get_password_hash()
        if not password_hash:
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication setup required", "code": "AUTH_SETUP_REQUIRED"},
            )

        token = request.cookies.get(AUTH_COOKIE_NAME)
        if not token:
            auth_header = request.headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]

        if not token or not validate_session(token):
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required", "code": "AUTH_REQUIRED"},
            )

        return await call_next(request)
