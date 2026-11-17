"""权限依赖与归属校验：越权访问统一返回 404，避免泄露资源存在性。"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

from fastapi import HTTPException, Request, status

from backend.modules.auth.middleware import AUTH_COOKIE_NAME, _is_local_request
from backend.modules.multiuser.identity import AuthUser, anonymous_admin, resolve_session_user
from backend.modules.multiuser.settings import load_settings


# 请求级当前用户；FastAPI 每请求独立 task，ContextVar 随 task 隔离
current_user_ctx: ContextVar[Optional[AuthUser]] = ContextVar("countbot_current_user", default=None)


def get_request_user() -> Optional[AuthUser]:
    """读取当前请求身份（无请求上下文时返回 None）。"""
    return current_user_ctx.get()


def _extract_token(request: Request) -> Optional[str]:
    token = request.cookies.get(AUTH_COOKIE_NAME)
    if token:
        return token
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return None


def _auth_required() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"detail": "请先登录", "code": "AUTH_REQUIRED"},
    )


def _forbidden(code: str = "FORBIDDEN", detail: str = "无权限") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"detail": detail, "code": code},
    )


def not_found() -> HTTPException:
    """资源不存在或越权：对外统一 404。"""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"detail": "资源不存在", "code": "NOT_FOUND"},
    )


async def get_current_user(request: Request) -> Optional[AuthUser]:
    """解析当前请求身份；未登录返回 None，结果缓存在 ``request.state``。"""
    cached = getattr(request.state, "auth_user", None)
    if cached is not None:
        current_user_ctx.set(cached)
        return cached

    settings = await load_settings()
    token = _extract_token(request)

    # 显式会话优先，避免本机直连把普通用户提升为管理员
    if token:
        session_user = await resolve_session_user(token, require_active=True)
        if session_user is not None:
            request.state.auth_user = session_user
            current_user_ctx.set(session_user)
            return session_user

    # 无有效会话且本机直连：桌面单用户模式视为管理员；多用户模式下该旁路
    # 恒定关闭（回环请求同样要带有效会话），部署级开关可整体关闭
    if (
        settings.allow_local_admin_bypass
        and not getattr(settings, "enabled", False)
        and _is_local_request(request)
    ):
        user = anonymous_admin()
        request.state.auth_user = user
        current_user_ctx.set(user)
        return user

    user = await resolve_session_user(token, require_active=True)
    request.state.auth_user = user
    current_user_ctx.set(user)
    return user


async def require_authenticated(request: Request) -> AuthUser:
    """要求已登录（不校验状态）。"""
    user = await get_current_user(request)
    if user is None:
        raise _auth_required()
    return user


async def require_active_user(request: Request) -> AuthUser:
    """要求已登录且状态为 active；待审批/禁用直接拒绝。"""
    user = await get_current_user(request)
    if user is None:
        raise _auth_required()
    if not user.is_active:
        raise _forbidden(
            code="ACCOUNT_PENDING" if user.status == "pending" else "ACCOUNT_DISABLED",
            detail="账号待审批" if user.status == "pending" else "账号已被禁用",
        )
    return user


async def require_admin(request: Request) -> AuthUser:
    """要求管理员身份。"""
    user = await require_active_user(request)
    if not user.is_admin:
        raise _forbidden(code="ADMIN_REQUIRED", detail="需要管理员权限")
    return user


def ensure_owner_or_admin(user: AuthUser, owner_id: Optional[str]) -> None:
    """对象级归属校验：管理员放行，普通用户须与 owner 一致。"""
    if user is None or not isinstance(user, AuthUser):
        return
    if user.is_admin:
        return
    if not owner_id or owner_id != user.id:
        raise not_found()


def owner_scope(user: AuthUser) -> Optional[str]:
    """当前用户的归属过滤值：管理员为 None（可见全部）。"""
    if user is None or not isinstance(user, AuthUser):
        return None
    return None if user.is_admin else (user.id or None)
