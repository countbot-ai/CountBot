"""Remote access authentication middleware."""

from typing import Optional

from fastapi.responses import RedirectResponse
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from backend.modules.auth.utils import validate_session

AUTH_COOKIE_NAME = "CountBot_token"

PUBLIC_FRONTEND_PREFIXES = (
    "/login",
    "/assets/",
    "/favicon.ico",
)

PUBLIC_AUTH_ROUTES = {
    ("GET", "/api/auth/status"),
    ("POST", "/api/auth/login"),
}

SETUP_ROUTE = ("POST", "/api/auth/setup")

LOCAL_IPS = {"127.0.0.1", "::1"}

PROXY_HEADERS = {
    "x-forwarded-for",
    "x-real-ip",
    "x-forwarded-host",
    "x-forwarded-proto",
    "forwarded",
    "via",
    "x-forwarded-server",
    "x-cluster-client-ip",
    "cf-connecting-ip",
    "true-client-ip",
}


def _get_real_client_ip(request: Request) -> Optional[str]:
    if request.client is None:
        logger.warning("Unable to get client IP: request.client is None")
        return None

    client_ip = request.client.host
    if not client_ip:
        logger.warning("Unable to get client IP: client.host is empty")
        return None

    return client_ip


def _has_proxy_headers(request: Request) -> bool:
    request_headers = {k.lower() for k in request.headers.keys()}
    return bool(PROXY_HEADERS & request_headers)


def _is_local_request(request: Request) -> bool:
    client_ip = _get_real_client_ip(request)
    if client_ip is None:
        return False

    if _has_proxy_headers(request):
        logger.debug(f"Proxy detected (socket IP: {client_ip}), treating as remote")
        return False

    return client_ip in LOCAL_IPS


def _get_token_from_request(request: Request) -> Optional[str]:
    token = request.cookies.get(AUTH_COOKIE_NAME)
    if token:
        return token

    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]

    return None


def _is_public_frontend_path(path: str) -> bool:
    if path in ("/login", "/login/"):
        return True

    return any(path.startswith(prefix) for prefix in PUBLIC_FRONTEND_PREFIXES if prefix != "/login")


def _is_public_auth_route(path: str, method: str, is_local: bool, auth_enabled: bool) -> bool:
    route_key = (method.upper(), path)
    if route_key in PUBLIC_AUTH_ROUTES:
        return True

    # First-time bootstrap is allowed only from a direct local request.
    if route_key == SETUP_ROUTE and is_local and not auth_enabled:
        return True

    return False


def _is_browser_navigation(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    return request.method.upper() == "GET" and "text/html" in accept


class RemoteAuthMiddleware(BaseHTTPMiddleware):
    """Block every unauthenticated entrypoint except the login flow."""

    def __init__(self, app, get_password_hash_fn=None):
        super().__init__(app)
        self._get_password_hash = get_password_hash_fn

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        method = request.method.upper()
        client_ip = _get_real_client_ip(request)
        is_local = _is_local_request(request)

        password_hash = await self._get_password_hash_safe()
        auth_enabled = bool(password_hash)

        if _is_public_frontend_path(path):
            return await call_next(request)

        if _is_public_auth_route(path, method, is_local, auth_enabled):
            return await call_next(request)

        token = _get_token_from_request(request)
        username = validate_session(token) if token else None
        if username:
            logger.debug(f"Authenticated access: {client_ip} ({username}) -> {path}")
            return await call_next(request)

        if path.startswith("/api/"):
            logger.warning(f"Unauthorized API access attempt: {client_ip} -> {path}")
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required", "code": "AUTH_REQUIRED"},
            )

        if path.startswith("/ws/"):
            logger.warning(f"Unauthorized WebSocket access attempt: {client_ip} -> {path}")
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required", "code": "AUTH_REQUIRED"},
            )

        if _is_browser_navigation(request):
            return RedirectResponse(url="/login", status_code=307)

        logger.warning(f"Unauthorized frontend access attempt: {client_ip} -> {path}")
        return JSONResponse(
            status_code=401,
            content={"detail": "Authentication required", "code": "AUTH_REQUIRED"},
        )

    async def _get_password_hash_safe(self) -> str:
        try:
            if self._get_password_hash:
                return await self._get_password_hash()
        except Exception:
            logger.exception("Failed to load auth password hash")

        return ""
