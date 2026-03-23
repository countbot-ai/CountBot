"""Authentication API endpoints."""

import json
import threading
import time
from typing import Dict, Tuple

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel

from backend.modules.auth.middleware import (
    AUTH_COOKIE_NAME,
    _is_local_request,
    clear_remote_setup_secret,
    request_has_valid_remote_setup_secret,
)
from backend.modules.auth.utils import (
    TOKEN_EXPIRY,
    create_session,
    hash_password,
    needs_password_rehash,
    revoke_all_sessions,
    revoke_session,
    validate_password,
    validate_session,
    validate_username,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

_AUTH_KEY_USERNAME = "auth.username"
_AUTH_KEY_PASSWORD_HASH = "auth.password_hash"

_RATE_LIMIT_WINDOW_SECONDS = 15 * 60
_RATE_LIMIT_MAX_ATTEMPTS = 5
_RATE_LIMIT_LOCKOUT_SECONDS = 15 * 60
_auth_attempt_lock = threading.Lock()
_auth_attempts: Dict[str, list[float]] = {}
_auth_lockouts: Dict[str, float] = {}


class LoginRequest(BaseModel):
    username: str
    password: str


class SetPasswordRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


async def get_stored_credentials() -> Tuple[str, str]:
    """Load stored username and password hash from settings."""
    from sqlalchemy import select
    from backend.database import AsyncSessionLocal
    from backend.models.setting import Setting

    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Setting).where(Setting.key.in_([_AUTH_KEY_USERNAME, _AUTH_KEY_PASSWORD_HASH]))
            )
            settings = {s.key: s.value for s in result.scalars().all()}
            username = json.loads(settings.get(_AUTH_KEY_USERNAME, '""'))
            password_hash = json.loads(settings.get(_AUTH_KEY_PASSWORD_HASH, '""'))
            return username or "", password_hash or ""
    except Exception as exc:
        logger.warning(f"Failed to get stored credentials: {exc}")
        return "", ""


async def get_password_hash() -> str:
    _, password_hash = await get_stored_credentials()
    return password_hash


async def save_credentials(username: str, password_hash: str):
    from backend.database import AsyncSessionLocal
    from backend.models.setting import Setting

    async with AsyncSessionLocal() as session:
        for key, value in ((_AUTH_KEY_USERNAME, username), (_AUTH_KEY_PASSWORD_HASH, password_hash)):
            setting = Setting(key=key, value=json.dumps(value))
            await session.merge(setting)
        await session.commit()


def _client_ip(request: Request) -> str:
    return request.client.host if request.client and request.client.host else "unknown"


def _auth_rate_limit_key(action: str, request: Request, username: str = "") -> str:
    normalized_username = username.strip().lower()
    return f"{action}:{_client_ip(request)}:{normalized_username}"


def _prune_attempts(now: float) -> None:
    stale_before = now - _RATE_LIMIT_WINDOW_SECONDS

    expired_attempt_keys = []
    for key, attempts in _auth_attempts.items():
        filtered = [ts for ts in attempts if ts >= stale_before]
        if filtered:
            _auth_attempts[key] = filtered
        else:
            expired_attempt_keys.append(key)

    for key in expired_attempt_keys:
        _auth_attempts.pop(key, None)

    expired_lockouts = [key for key, until in _auth_lockouts.items() if until <= now]
    for key in expired_lockouts:
        _auth_lockouts.pop(key, None)


def _check_rate_limit(action: str, request: Request, username: str = "") -> Tuple[bool, int]:
    key = _auth_rate_limit_key(action, request, username)
    now = time.time()

    with _auth_attempt_lock:
        _prune_attempts(now)
        locked_until = _auth_lockouts.get(key)
        if locked_until and locked_until > now:
            return False, max(1, int(locked_until - now))

    return True, 0


def _record_auth_failure(action: str, request: Request, username: str = "") -> None:
    key = _auth_rate_limit_key(action, request, username)
    now = time.time()

    with _auth_attempt_lock:
        _prune_attempts(now)
        attempts = _auth_attempts.setdefault(key, [])
        attempts.append(now)
        if len(attempts) >= _RATE_LIMIT_MAX_ATTEMPTS:
            _auth_lockouts[key] = now + _RATE_LIMIT_LOCKOUT_SECONDS


def _clear_auth_failures(action: str, request: Request, username: str = "") -> None:
    key = _auth_rate_limit_key(action, request, username)
    with _auth_attempt_lock:
        _auth_attempts.pop(key, None)
        _auth_lockouts.pop(key, None)


def _set_auth_cookie(response: JSONResponse, token: str, request: Request) -> None:
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
        max_age=TOKEN_EXPIRY,
        path="/",
    )


def _auth_required_response() -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={"detail": "请先登录", "code": "AUTH_REQUIRED"},
    )


@router.get("/status")
async def auth_status(request: Request):
    """Public auth bootstrap endpoint used by the login page."""
    is_local = _is_local_request(request)
    _, password_hash = await get_stored_credentials()
    auth_enabled = bool(password_hash)

    token = request.cookies.get(AUTH_COOKIE_NAME)
    if not token:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

    authenticated = bool(validate_session(token) if token else False)
    bind_host = getattr(request.app.state, "bind_host", "127.0.0.1")
    remote_access_enabled = bind_host == "0.0.0.0"

    return {
        "is_local": is_local,
        "auth_enabled": auth_enabled,
        "authenticated": authenticated,
        "remote_access_enabled": remote_access_enabled,
        "setup_allowed": not auth_enabled and (is_local or request_has_valid_remote_setup_secret(request)),
    }


@router.post("/setup")
async def setup_password(data: SetPasswordRequest, request: Request):
    """Allow first-time password bootstrap from local requests or a valid remote setup entry."""
    if not _is_local_request(request) and not request_has_valid_remote_setup_secret(request):
        return JSONResponse(
            status_code=403,
            content={"detail": "首次初始化只能在本机完成", "code": "SETUP_LOCAL_ONLY"},
        )

    allowed, retry_after = _check_rate_limit("setup", request, data.username)
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={"detail": f"尝试过于频繁，请 {retry_after} 秒后再试", "code": "RATE_LIMITED"},
        )

    _, existing_hash = await get_stored_credentials()
    if existing_hash:
        return JSONResponse(
            status_code=400,
            content={"detail": "密码已设置，请使用登录接口", "code": "AUTH_ALREADY_INITIALIZED"},
        )

    valid_username, username_msg = validate_username(data.username)
    if not valid_username:
        _record_auth_failure("setup", request, data.username)
        return JSONResponse(status_code=400, content={"detail": username_msg})

    valid, msg = validate_password(data.password)
    if not valid:
        _record_auth_failure("setup", request, data.username)
        return JSONResponse(status_code=400, content={"detail": msg})

    hashed = hash_password(data.password)
    await save_credentials(data.username.strip(), hashed)
    clear_remote_setup_secret(request.app)
    _clear_auth_failures("setup", request, data.username)
    logger.info(f"Remote auth password set for user: {data.username.strip()}")

    token = create_session(data.username.strip())
    response = JSONResponse(
        content={
            "success": True,
            "message": "密码设置成功",
        }
    )
    _set_auth_cookie(response, token, request)
    return response


@router.post("/login")
async def login(data: LoginRequest, request: Request):
    """Authenticate a user and issue a cookie-backed session."""
    allowed, retry_after = _check_rate_limit("login", request, data.username)
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={"detail": f"尝试过于频繁，请 {retry_after} 秒后再试", "code": "RATE_LIMITED"},
        )

    stored_username, stored_hash = await get_stored_credentials()
    if not stored_hash:
        return JSONResponse(
            status_code=403,
            content={"detail": "管理员尚未完成初始化，请先设置账号和密码", "code": "AUTH_NOT_INITIALIZED"},
        )

    normalized_username = data.username.strip()
    valid_username, _ = validate_username(normalized_username)
    if not valid_username:
        _record_auth_failure("login", request, normalized_username)
        return JSONResponse(
            status_code=401,
            content={"detail": "用户名或密码错误"},
        )

    if normalized_username != stored_username or not verify_password(data.password, stored_hash):
        _record_auth_failure("login", request, normalized_username)
        return JSONResponse(
            status_code=401,
            content={"detail": "用户名或密码错误"},
        )

    if needs_password_rehash(stored_hash):
        await save_credentials(stored_username, hash_password(data.password))

    _clear_auth_failures("login", request, normalized_username)
    token = create_session(stored_username)
    response = JSONResponse(
        content={
            "success": True,
            "message": "登录成功",
        }
    )
    _set_auth_cookie(response, token, request)
    return response


@router.post("/logout")
async def logout(request: Request):
    token = request.cookies.get(AUTH_COOKIE_NAME)
    if token:
        revoke_session(token)

    response = JSONResponse(content={"success": True})
    response.delete_cookie(AUTH_COOKIE_NAME, path="/")
    return response


@router.post("/change-password")
async def change_password(data: ChangePasswordRequest, request: Request):
    token = request.cookies.get(AUTH_COOKIE_NAME)
    username = validate_session(token) if token else None
    if not username:
        return _auth_required_response()

    allowed, retry_after = _check_rate_limit("change-password", request, username)
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={"detail": f"尝试过于频繁，请 {retry_after} 秒后再试", "code": "RATE_LIMITED"},
        )

    stored_username, stored_hash = await get_stored_credentials()
    if not stored_hash or username != stored_username:
        return _auth_required_response()

    if not verify_password(data.old_password, stored_hash):
        _record_auth_failure("change-password", request, username)
        return JSONResponse(
            status_code=401,
            content={"detail": "旧密码错误"},
        )

    valid, msg = validate_password(data.new_password)
    if not valid:
        _record_auth_failure("change-password", request, username)
        return JSONResponse(status_code=400, content={"detail": msg})

    await save_credentials(stored_username, hash_password(data.new_password))
    revoke_all_sessions(stored_username)
    _clear_auth_failures("change-password", request, username)
    logger.info(f"Password changed for user: {stored_username}")

    return {"success": True, "message": "密码修改成功，请重新登录"}
