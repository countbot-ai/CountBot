"""认证 API 端点"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from loguru import logger

from backend.modules.auth.utils import (
    validate_password,
    hash_password,
    verify_password,
    create_session,
    revoke_session,
    validate_session,
)
from backend.modules.auth.middleware import _is_local_request

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class SetPasswordRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


# ============================================================================
# 密码存储（通过 settings 表）
# ============================================================================

_AUTH_KEY_USERNAME = "auth.username"
_AUTH_KEY_PASSWORD_HASH = "auth.password_hash"


async def get_stored_credentials() -> tuple[str, str]:
    """获取存储的用户名和密码哈希"""
    from sqlalchemy import select
    from backend.database import AsyncSessionLocal
    from backend.models.setting import Setting

    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Setting).where(Setting.key.in_([_AUTH_KEY_USERNAME, _AUTH_KEY_PASSWORD_HASH]))
            )
            settings = {s.key: s.value for s in result.scalars().all()}
            import json
            username = json.loads(settings.get(_AUTH_KEY_USERNAME, '""'))
            password_hash = json.loads(settings.get(_AUTH_KEY_PASSWORD_HASH, '""'))
            return username or "", password_hash or ""
    except Exception as e:
        logger.warning(f"Failed to get stored credentials: {e}")
        return "", ""


async def get_password_hash() -> str:
    """获取密码哈希（供中间件使用）"""
    _, password_hash = await get_stored_credentials()
    return password_hash


async def save_credentials(username: str, password_hash: str):
    """保存认证凭据到 settings 表"""
    import json
    from backend.database import AsyncSessionLocal
    from backend.models.setting import Setting

    async with AsyncSessionLocal() as session:
        for key, value in [(_AUTH_KEY_USERNAME, username), (_AUTH_KEY_PASSWORD_HASH, password_hash)]:
            setting = Setting(key=key, value=json.dumps(value))
            await session.merge(setting)
        await session.commit()


# ============================================================================
# API 端点
# ============================================================================


@router.get("/status")
async def auth_status(request: Request):
    """获取认证状态

    返回：
    - is_local: 是否本地访问
    - auth_enabled: 是否已设置密码（启用远程认证）
    - authenticated: 当前请求是否已认证
    - remote_access_enabled: 服务器是否开启了远程访问（绑定 0.0.0.0）
    """
    is_local = _is_local_request(request)
    _, password_hash = await get_stored_credentials()
    auth_enabled = bool(password_hash)

    # 检查当前 token
    token = request.cookies.get("CountBot_token")
    if not token:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

    authenticated = is_local or bool(validate_session(token) if token else False)

    # 检查服务器是否绑定了 0.0.0.0（开启远程访问）
    bind_host = getattr(request.app.state, "bind_host", "127.0.0.1")
    remote_access_enabled = bind_host == "0.0.0.0"

    return {
        "is_local": is_local,
        "auth_enabled": auth_enabled,
        "authenticated": authenticated,
        "remote_access_enabled": remote_access_enabled,
    }


@router.post("/setup")
async def setup_password(data: SetPasswordRequest, request: Request):
    """首次设置密码（仅当未设置密码时可用）"""
    _, existing_hash = await get_stored_credentials()
    if existing_hash:
        return JSONResponse(
            status_code=400,
            content={"detail": "密码已设置，请使用修改密码接口"},
        )

    # 验证密码强度
    valid, msg = validate_password(data.password)
    if not valid:
        return JSONResponse(status_code=400, content={"detail": msg})

    # 保存
    hashed = hash_password(data.password)
    await save_credentials(data.username, hashed)
    logger.info(f"Remote auth password set for user: {data.username}")

    # 自动登录
    token = create_session(data.username)
    response = JSONResponse(content={
        "success": True,
        "message": "密码设置成功",
        "token": token,
    })
    response.set_cookie(
        key="CountBot_token",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=86400,
    )
    return response


@router.post("/login")
async def login(data: LoginRequest):
    """登录"""
    stored_username, stored_hash = await get_stored_credentials()

    if not stored_hash:
        return JSONResponse(
            status_code=400,
            content={"detail": "尚未设置密码，请先设置"},
        )

    # 验证用户名和密码
    if data.username != stored_username:
        return JSONResponse(
            status_code=401,
            content={"detail": "用户名或密码错误"},
        )

    if not verify_password(data.password, stored_hash):
        return JSONResponse(
            status_code=401,
            content={"detail": "用户名或密码错误"},
        )

    # 创建 session
    token = create_session(data.username)
    response = JSONResponse(content={
        "success": True,
        "message": "登录成功",
        "token": token,
    })
    response.set_cookie(
        key="CountBot_token",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=86400,
    )
    return response


@router.post("/logout")
async def logout(request: Request):
    """登出"""
    token = request.cookies.get("CountBot_token")
    if token:
        revoke_session(token)

    response = JSONResponse(content={"success": True})
    response.delete_cookie("CountBot_token")
    return response


@router.post("/change-password")
async def change_password(data: ChangePasswordRequest, request: Request):
    """修改密码（需要已认证或本地访问）"""
    is_local = _is_local_request(request)

    # 非本地访问需要验证当前 token
    if not is_local:
        token = request.cookies.get("CountBot_token")
        if not token or not validate_session(token):
            return JSONResponse(
                status_code=401,
                content={"detail": "请先登录"},
            )

    stored_username, stored_hash = await get_stored_credentials()

    if not stored_hash:
        return JSONResponse(
            status_code=400,
            content={"detail": "尚未设置密码"},
        )

    # 验证旧密码
    if not verify_password(data.old_password, stored_hash):
        return JSONResponse(
            status_code=401,
            content={"detail": "旧密码错误"},
        )

    # 验证新密码强度
    valid, msg = validate_password(data.new_password)
    if not valid:
        return JSONResponse(status_code=400, content={"detail": msg})

    # 保存新密码
    new_hash = hash_password(data.new_password)
    await save_credentials(stored_username, new_hash)
    logger.info(f"Password changed for user: {stored_username}")

    return {"success": True, "message": "密码修改成功"}
