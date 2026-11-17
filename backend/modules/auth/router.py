"""Authentication API endpoints."""

import json
import threading
import time
from typing import Dict, Optional, Tuple

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
from backend.utils.runtime_env import is_public_bind_host

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


class RegisterRequest(BaseModel):
    username: str
    password: str
    display_name: Optional[str] = None


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


# ---------------------------------------------------------------------------
# 多用户身份同步辅助：管理员凭据需同时写入 settings 与 users 表
# ---------------------------------------------------------------------------


async def _sync_admin_row(username: str, password_hash: str) -> None:
    try:
        from backend.modules.multiuser.bootstrap import sync_admin_credentials

        await sync_admin_credentials(username, password_hash)
    except Exception as exc:
        logger.warning(f"Failed to sync admin user row: {exc}")


async def _load_user_by_username(username: str):
    try:
        from backend.modules.multiuser.identity import get_user_by_username

        return await get_user_by_username(username)
    except Exception as exc:
        logger.warning(f"Failed to load user {username!r}: {exc}")
        return None


async def _issue_session_for(username: str) -> str:
    """签发会话；能定位到用户行时带上 user_id。"""
    user = await _load_user_by_username(username)
    return create_session(username, user_id=(user.id if user else None))


async def _update_user_password_hash(user_id: str, password_hash: str) -> None:
    from backend.database import AsyncSessionLocal
    from backend.models.user import User

    try:
        async with AsyncSessionLocal() as session:
            user = await session.get(User, user_id)
            if user is not None:
                user.password_hash = password_hash
                await session.commit()
    except Exception as exc:
        logger.warning(f"Failed to rehash user password: {exc}")


async def _touch_last_login(user_id) -> None:
    if not user_id:
        return
    from datetime import datetime

    from backend.database import AsyncSessionLocal
    from backend.models.user import User

    try:
        async with AsyncSessionLocal() as session:
            user = await session.get(User, user_id)
            if user is not None:
                user.last_login_at = datetime.utcnow()
                await session.commit()
    except Exception as exc:
        logger.debug(f"Failed to update last_login_at: {exc}")


async def _audit_login_success(request: Request, user_id, username: str) -> None:
    try:
        from backend.modules.multiuser import audit
        from backend.modules.multiuser.identity import AuthUser

        await audit.record_audit(
            audit.ACTION_LOGIN_SUCCESS,
            actor=AuthUser(id=user_id or "", username=username),
            request=request,
        )
    except Exception as exc:
        logger.debug(f"Failed to audit login success: {exc}")


async def _audit_login_failure(request: Request, username: str) -> None:
    try:
        from backend.modules.multiuser import audit

        await audit.record_audit(
            audit.ACTION_LOGIN_FAILURE,
            target=username,
            request=request,
        )
    except Exception as exc:
        logger.debug(f"Failed to audit login failure: {exc}")


async def _is_admin_session_token(token: Optional[str]) -> bool:
    """单用户模式的管理员会话没有 users 记录，按 settings 中的管理员用户名确认。"""
    username = validate_session(token) if token else None
    if not username:
        return False
    stored_username, _ = await get_stored_credentials()
    return bool(stored_username and username == stored_username)


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


def _login_lock_suffix(username: str) -> str:
    return f":{(username or '').strip().lower()}"


def login_lock_remaining(username: str) -> int:
    """该用户名的登录锁定剩余秒数（跨来源 IP 取最大值）；0 表示未锁定。"""
    suffix = _login_lock_suffix(username)
    if suffix == ":":
        return 0
    now = time.time()
    remaining = 0
    with _auth_attempt_lock:
        for key, until in _auth_lockouts.items():
            if key.startswith("login:") and key.endswith(suffix) and until > now:
                remaining = max(remaining, int(until - now))
    return remaining


def clear_login_lockouts(username: str) -> int:
    """清除该用户名在所有来源 IP 上的登录失败记录与锁定，返回清除的键数量。"""
    suffix = _login_lock_suffix(username)
    if suffix == ":":
        return 0
    with _auth_attempt_lock:
        keys = [
            key
            for key in set(_auth_attempts) | set(_auth_lockouts)
            if key.startswith("login:") and key.endswith(suffix)
        ]
        for key in keys:
            _auth_attempts.pop(key, None)
            _auth_lockouts.pop(key, None)
    return len(keys)


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

    bind_host = getattr(request.app.state, "bind_host", "127.0.0.1")
    remote_access_enabled = is_public_bind_host(bind_host)

    # 多用户信息：前端据此显示注册入口与角色相关界面
    multiuser_enabled = False
    registration_open = False
    approval_mode = "manual"
    role = None
    authenticated = False
    username = None
    display_name = None
    try:
        from backend.modules.multiuser.identity import resolve_session_user
        from backend.modules.multiuser.settings import load_settings

        settings = await load_settings()
        multiuser_enabled = settings.enabled
        registration_open = settings.registration_allowed
        approval_mode = settings.approval

        current_user = await resolve_session_user(token, require_active=True) if token else None
        if current_user is not None:
            role = current_user.role
            authenticated = True
            # 侧栏需要展示当前登录者身份，仅返回「已认证」无法区分账号
            username = current_user.username
            display_name = current_user.display_name
        elif await _is_admin_session_token(token):
            # 单用户模式的管理员会话没有 users 记录，需单独识别为已登录
            authenticated = True
            role = "admin"
    except Exception as exc:  # 多用户未就绪时不影响登录页引导
        logger.debug(f"auth_status multiuser info unavailable: {exc}")
        authenticated = await _is_admin_session_token(token)

    return {
        "is_local": is_local,
        "auth_enabled": auth_enabled,
        "authenticated": authenticated,
        "remote_access_enabled": remote_access_enabled,
        "setup_allowed": not auth_enabled and (is_local or request_has_valid_remote_setup_secret(request)),
        "multiuser_enabled": multiuser_enabled,
        "registration_open": registration_open,
        "approval_mode": approval_mode,
        "role": role,
        "username": username,
        "display_name": display_name,
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
    await _sync_admin_row(data.username.strip(), hashed)
    clear_remote_setup_secret(request.app)
    _clear_auth_failures("setup", request, data.username)
    logger.info(f"Remote auth password set for user: {data.username.strip()}")

    token = await _issue_session_for(data.username.strip())
    response = JSONResponse(
        content={
            "success": True,
            "message": "密码设置成功",
        }
    )
    _set_auth_cookie(response, token, request)
    return response


@router.post("/register")
async def register(data: RegisterRequest, request: Request):
    """开放注册；仅在多用户开启且注册开放时可用，否则返回 403。"""
    from backend.modules.multiuser.settings import load_settings

    settings = await load_settings()
    if not settings.registration_allowed:
        return JSONResponse(
            status_code=403,
            content={"detail": "当前未开放注册", "code": "REGISTRATION_CLOSED"},
        )

    allowed, retry_after = _check_rate_limit("register", request, data.username)
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={"detail": f"尝试过于频繁，请 {retry_after} 秒后再试", "code": "RATE_LIMITED"},
        )

    valid_username, username_msg = validate_username(data.username)
    if not valid_username:
        _record_auth_failure("register", request, data.username)
        return JSONResponse(status_code=400, content={"detail": username_msg})

    valid_password, password_msg = validate_password(data.password)
    if not valid_password:
        _record_auth_failure("register", request, data.username)
        return JSONResponse(status_code=400, content={"detail": password_msg})

    from backend.database import AsyncSessionLocal
    from backend.models.user import STATUS_ACTIVE, STATUS_PENDING, User
    from backend.modules.multiuser import audit
    from backend.modules.multiuser.bootstrap import count_users

    username = data.username.strip()
    max_users = settings.max_users
    if max_users and await count_users() >= max_users:
        return JSONResponse(
            status_code=403,
            content={"detail": "用户数已达上限", "code": "USER_LIMIT_REACHED"},
        )

    existing = await _load_user_by_username(username)
    if existing is not None:
        # 统一文案，避免通过注册接口枚举已存在的账号
        _record_auth_failure("register", request, username)
        return JSONResponse(
            status_code=409,
            content={"detail": "该账号不可用，请更换后重试", "code": "ACCOUNT_UNAVAILABLE"},
        )

    import uuid as _uuid
    from datetime import datetime as _dt

    status_value = STATUS_ACTIVE if settings.approval_auto else STATUS_PENDING
    user_id = str(_uuid.uuid4())
    async with AsyncSessionLocal() as session:
        session.add(
            User(
                id=user_id,
                username=username,
                password_hash=hash_password(data.password),
                role="user",
                status=status_value,
                display_name=(data.display_name or username).strip(),
                approved_at=_dt.utcnow() if status_value == STATUS_ACTIVE else None,
            )
        )
        await session.commit()

    await audit.record_audit(
        audit.ACTION_REGISTER,
        target=username,
        detail=f"status={status_value}",
        request=request,
    )
    _clear_auth_failures("register", request, username)
    logger.info(f"New user registered: {username} ({status_value})")

    if status_value != STATUS_ACTIVE:
        return JSONResponse(
            status_code=201,
            content={
                "success": True,
                "status": status_value,
                "message": "注册成功，请等待管理员审批",
            },
        )

    token = create_session(username, user_id=user_id)
    response = JSONResponse(
        status_code=201,
        content={
            "success": True,
            "status": status_value,
            "message": "注册成功",
        },
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

    # 优先按 users 表校验，用户行不存在时回落到 settings
    user = await _load_user_by_username(normalized_username)
    if user is not None and user.password_hash:
        if not verify_password(data.password, user.password_hash):
            _record_auth_failure("login", request, normalized_username)
            await _audit_login_failure(request, normalized_username)
            return JSONResponse(
                status_code=401,
                content={"detail": "用户名或密码错误"},
            )

        # 多用户关闭后只保留管理员账号，普通用户立即失效
        from backend.modules.multiuser.settings import load_settings

        if not (await load_settings()).enabled and user.role != "admin":
            return JSONResponse(
                status_code=403,
                content={"detail": "多用户功能已关闭", "code": "MULTIUSER_DISABLED"},
            )

        # 状态判定：待审批 / 禁用一律拒绝，且不泄露账号是否存在
        if user.status == "pending":
            _record_auth_failure("login", request, normalized_username)
            return JSONResponse(
                status_code=403,
                content={"detail": "账号待管理员审批", "code": "ACCOUNT_PENDING"},
            )
        if user.status != "active":
            _record_auth_failure("login", request, normalized_username)
            return JSONResponse(
                status_code=403,
                content={"detail": "账号已被禁用", "code": "ACCOUNT_DISABLED"},
            )

        if needs_password_rehash(user.password_hash):
            await _update_user_password_hash(user.id, hash_password(data.password))

        source_username = user.username
        source_user_id = user.id
    else:
        if normalized_username != stored_username or not verify_password(data.password, stored_hash):
            _record_auth_failure("login", request, normalized_username)
            await _audit_login_failure(request, normalized_username)
            return JSONResponse(
                status_code=401,
                content={"detail": "用户名或密码错误"},
            )

        if needs_password_rehash(stored_hash):
            await save_credentials(stored_username, hash_password(data.password))

        source_username = stored_username
        source_user_id = None

    _clear_auth_failures("login", request, normalized_username)
    token = create_session(source_username, user_id=source_user_id)
    await _touch_last_login(source_user_id)
    await _audit_login_success(request, source_user_id, source_username)

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
    """修改自己的密码（管理员与普通用户都支持）。"""
    token = request.cookies.get(AUTH_COOKIE_NAME)
    if not token:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

    from backend.modules.multiuser.identity import resolve_session_user

    current_user = await resolve_session_user(token, require_active=True) if token else None
    if current_user is None:
        return _auth_required_response()

    username = current_user.username
    allowed, retry_after = _check_rate_limit("change-password", request, username)
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={"detail": f"尝试过于频繁，请 {retry_after} 秒后再试", "code": "RATE_LIMITED"},
        )

    # 普通用户改自己的密码；管理员沿用 settings 中的凭据
    is_admin = current_user.is_admin
    if is_admin:
        stored_username, stored_hash = await get_stored_credentials()
        if not stored_hash or username != stored_username:
            return _auth_required_response()
        current_hash = stored_hash
    else:
        user_row = await _load_user_by_username(username)
        if user_row is None or not user_row.password_hash:
            return _auth_required_response()
        current_hash = user_row.password_hash

    if not verify_password(data.old_password, current_hash):
        _record_auth_failure("change-password", request, username)
        return JSONResponse(
            status_code=401,
            content={"detail": "旧密码错误"},
        )

    valid, msg = validate_password(data.new_password)
    if not valid:
        _record_auth_failure("change-password", request, username)
        return JSONResponse(status_code=400, content={"detail": msg})

    new_hash = hash_password(data.new_password)
    if is_admin:
        await save_credentials(username, new_hash)
        await _sync_admin_row(username, new_hash)
        revoke_all_sessions(username)
    else:
        await _update_user_password_hash(current_user.id, new_hash)
        from backend.modules.multiuser.identity import revoke_user_sessions

        revoke_user_sessions(current_user)

    _clear_auth_failures("change-password", request, username)
    logger.info(f"Password changed for user: {username}")

    return {"success": True, "message": "密码修改成功，请重新登录"}
