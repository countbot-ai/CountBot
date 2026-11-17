"""M1 身份底座测试：路由表、AuthUser 语义、设置读写与鉴权边界。"""

import uuid

import pytest
from fastapi import HTTPException

from backend.api.admin import router as admin_router
from backend.modules.multiuser.identity import AuthUser, anonymous_admin
from backend.modules.multiuser.permissions import ensure_owner_or_admin, owner_scope
from backend.modules.multiuser.settings import (
    APPROVAL_AUTO,
    APPROVAL_MANUAL,
    MODE_ISOLATED,
    MODE_SHARED,
    invalidate_cache,
    load_settings,
    save_settings,
)

TEST_USERNAME_PREFIX = "__m1_test_"
TEST_PASSWORD = "test-placeholder"


# ---------------------------------------------------------------------------
# 1. 路由表
# ---------------------------------------------------------------------------

EXPECTED_ADMIN_ROUTES = {
    ("/api/admin/users", ("GET",)),
    ("/api/admin/users", ("POST",)),
    ("/api/admin/users/{user_id}", ("PATCH",)),
    ("/api/admin/users/{user_id}", ("DELETE",)),
    ("/api/admin/users/{user_id}/password", ("PUT",)),
    ("/api/admin/users/{user_id}/unlock", ("POST",)),
    ("/api/admin/multiuser/settings", ("GET",)),
    ("/api/admin/multiuser/settings", ("PUT",)),
    ("/api/admin/audit-logs", ("GET",)),
    ("/api/admin/shared-models", ("GET",)),
}


def test_admin_route_table():
    actual = {
        (route.path, tuple(sorted(route.methods)))
        for route in admin_router.routes
        if hasattr(route, "methods")
    }
    assert actual == EXPECTED_ADMIN_ROUTES


def test_no_duplicate_admin_routes():
    keys = [
        (route.path, tuple(sorted(route.methods)))
        for route in admin_router.routes
        if hasattr(route, "methods")
    ]
    assert len(keys) == len(set(keys))


# ---------------------------------------------------------------------------
# 2. AuthUser 语义
# ---------------------------------------------------------------------------


def test_admin_owner_id_is_none():
    """管理员 owner_id 为空：历史数据与管理员数据 owner 都是 NULL。"""
    admin = AuthUser(id="abc", username="root", role="admin", status="active")
    assert admin.is_admin
    assert admin.owner_id is None
    assert owner_scope(admin) is None


def test_regular_user_owner_id_is_id():
    user = AuthUser(id="u-1", username="alice", role="user", status="active")
    assert not user.is_admin
    assert user.owner_id == "u-1"
    assert owner_scope(user) == "u-1"


def test_anonymous_admin_has_no_id():
    admin = anonymous_admin()
    assert admin.is_admin
    assert admin.id == ""


def test_ensure_owner_or_admin_allows_admin():
    admin = anonymous_admin()
    ensure_owner_or_admin(admin, "somebody-else")  # 不应抛异常


def test_ensure_owner_or_admin_allows_own_resource():
    user = AuthUser(id="u-1", username="alice", role="user", status="active")
    ensure_owner_or_admin(user, "u-1")  # 不应抛异常


def test_ensure_owner_or_admin_rejects_other_user_with_404():
    """越权访问返回 404（不暴露资源是否存在），而不是 403。"""
    user = AuthUser(id="u-1", username="alice", role="user", status="active")
    with pytest.raises(HTTPException) as exc:
        ensure_owner_or_admin(user, "u-2")
    assert exc.value.status_code == 404


def test_ensure_owner_or_admin_rejects_null_owner_for_user():
    """普通用户不能访问无归属（管理员）资源。"""
    user = AuthUser(id="u-1", username="alice", role="user", status="active")
    with pytest.raises(HTTPException) as exc:
        ensure_owner_or_admin(user, None)
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# 集成辅助：管理员状态快照 / 恢复，结束后还原 settings 与 users 表
# ---------------------------------------------------------------------------


async def _snapshot_admin_state() -> dict:
    from backend.modules.auth.router import get_stored_credentials
    from backend.modules.multiuser.bootstrap import get_admin_user

    username, password_hash = await get_stored_credentials()
    admin = await get_admin_user()
    return {
        "creds": (username, password_hash),
        "admin": (
            None
            if admin is None
            else {
                "id": admin.id,
                "username": admin.username,
                "password_hash": admin.password_hash,
                "role": admin.role,
                "status": admin.status,
                "display_name": admin.display_name,
            }
        ),
    }


async def _restore_admin_state(snapshot: dict) -> None:
    from sqlalchemy import select

    from backend.database import AsyncSessionLocal
    from backend.models.user import User
    from backend.modules.auth.router import save_credentials

    username, password_hash = snapshot["creds"]
    await save_credentials(username, password_hash)

    expected = snapshot["admin"]
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(select(User).where(User.role == "admin"))).scalars().all()
        if expected is None:
            for row in rows:
                await session.delete(row)
        else:
            for row in rows:
                if row.id != expected["id"]:
                    await session.delete(row)
            row = await session.get(User, expected["id"])
            if row is None:
                session.add(User(**expected))
            else:
                for key, value in expected.items():
                    setattr(row, key, value)
        await session.commit()

    invalidate_cache()


async def _reset_admin_rows() -> None:
    """删除全部管理员行，用于模拟「首次迁移」的干净状态。"""
    from sqlalchemy import select

    from backend.database import AsyncSessionLocal
    from backend.models.user import User

    async with AsyncSessionLocal() as session:
        rows = (await session.execute(select(User).where(User.role == "admin"))).scalars().all()
        for row in rows:
            await session.delete(row)
        await session.commit()


# ---------------------------------------------------------------------------
# 3. 开关读写
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multiuser_settings_defaults_and_roundtrip():
    from backend.database import init_db

    await init_db()
    invalidate_cache()

    original = await load_settings(use_cache=False)

    try:
        written = await save_settings(
            enabled=True,
            registration_open=True,
            approval=APPROVAL_AUTO,
            mode=MODE_ISOLATED,
            shared_providers=False,
            shared_skills_wiki_mcp=False,
        )
        assert written.enabled is True
        assert written.registration_open is True
        assert written.approval == APPROVAL_AUTO
        assert written.mode == MODE_ISOLATED
        assert written.shared_providers is False
        assert written.registration_allowed is True
        assert written.approval_auto is True

        # 非法枚举值不应写入
        await save_settings(approval="bogus", mode="bogus")
        reloaded = await load_settings(use_cache=False)
        assert reloaded.approval == APPROVAL_AUTO
        assert reloaded.mode == MODE_ISOLATED
    finally:
        await save_settings(
            enabled=original.enabled,
            registration_open=original.registration_open,
            approval=original.approval,
            mode=original.mode,
            shared_providers=original.shared_providers,
            shared_skills_wiki_mcp=original.shared_skills_wiki_mcp,
        )
        invalidate_cache()


def test_approval_and_mode_enum_values_are_stable():
    assert APPROVAL_MANUAL == "manual"
    assert APPROVAL_AUTO == "auto"
    assert MODE_SHARED == "shared"
    assert MODE_ISOLATED == "isolated"


def test_multiuser_settings_default_is_disabled():
    """未落库时应为「关闭 + 手动审批 + 共享模式」。"""
    from backend.modules.multiuser.settings import MultiuserSettings

    defaults = MultiuserSettings()
    assert defaults.enabled is False
    assert defaults.registration_open is False
    assert defaults.approval == APPROVAL_MANUAL
    assert defaults.mode == MODE_SHARED
    assert defaults.registration_allowed is False


# ---------------------------------------------------------------------------
# 4. 管理员迁移
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_admin_user_migrates_and_is_idempotent():
    from backend.database import init_db
    from backend.modules.auth.router import save_credentials
    from backend.modules.auth.utils import hash_password, verify_password
    from backend.modules.multiuser.bootstrap import ensure_admin_user

    await init_db()
    snapshot = await _snapshot_admin_state()

    try:
        # 造出「有存量凭据 + 无管理员行」的首次迁移状态
        await _reset_admin_rows()
        await save_credentials(f"{TEST_USERNAME_PREFIX}admin", hash_password(TEST_PASSWORD))

        first = await ensure_admin_user()
        second = await ensure_admin_user()

        assert first is not None, "应由存量凭据迁移生成管理员"
        assert second is not None
        assert first.id == second.id, "重复调用不应产生重复管理员"
        assert first.role == "admin"
        assert first.status == "active"
        assert first.username == f"{TEST_USERNAME_PREFIX}admin"
        assert verify_password(TEST_PASSWORD, first.password_hash)
    finally:
        await _restore_admin_state(snapshot)


@pytest.mark.asyncio
async def test_ensure_admin_user_noop_without_credentials():
    from backend.database import init_db
    from backend.modules.auth.router import save_credentials
    from backend.modules.multiuser.bootstrap import ensure_admin_user

    await init_db()
    snapshot = await _snapshot_admin_state()

    try:
        await _reset_admin_rows()
        await save_credentials("", "")
        assert await ensure_admin_user() is None
    finally:
        await _restore_admin_state(snapshot)


# ---------------------------------------------------------------------------
# 5. 鉴权边界（走真实 HTTP 栈）
# ---------------------------------------------------------------------------


def _client():
    from fastapi.testclient import TestClient

    from backend.app import app

    return TestClient(app)


@pytest.mark.asyncio
async def test_admin_api_requires_authentication_for_remote_client():
    """非本机、无会话的请求必须 401。"""
    from backend.database import init_db
    from backend.modules.auth.router import save_credentials
    from backend.modules.auth.utils import hash_password
    from backend.modules.multiuser.bootstrap import ensure_admin_user

    await init_db()
    snapshot = await _snapshot_admin_state()

    try:
        await save_credentials(f"{TEST_USERNAME_PREFIX}admin", hash_password(TEST_PASSWORD))
        await ensure_admin_user()

        response = _client().get("/api/admin/users")
        assert response.status_code == 401
        assert response.json()["code"] == "AUTH_REQUIRED"
    finally:
        await _restore_admin_state(snapshot)


@pytest.mark.asyncio
async def test_regular_user_session_cannot_reach_admin_endpoints():
    """已登录的普通用户访问管理接口必须 403。"""
    from backend.database import AsyncSessionLocal, init_db
    from backend.models.user import User
    from backend.modules.auth.router import save_credentials
    from backend.modules.auth.utils import create_session, hash_password, revoke_all_sessions
    from backend.modules.multiuser.bootstrap import ensure_admin_user

    await init_db()
    snapshot = await _snapshot_admin_state()
    from backend.modules.multiuser import settings as mu_settings

    original_enabled = (await mu_settings.load_settings(use_cache=False)).enabled
    await mu_settings.save_settings(enabled=True)

    user_id = str(uuid.uuid4())
    username = f"{TEST_USERNAME_PREFIX}{user_id[:8]}"

    try:
        await save_credentials(f"{TEST_USERNAME_PREFIX}admin", hash_password(TEST_PASSWORD))
        await ensure_admin_user()

        async with AsyncSessionLocal() as session:
            session.add(
                User(
                    id=user_id,
                    username=username,
                    password_hash=hash_password(TEST_PASSWORD),
                    role="user",
                    status="active",
                )
            )
            await session.commit()

        token = create_session(username, user_id=user_id)
        response = _client().get(
            "/api/admin/users",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "ADMIN_REQUIRED"
    finally:
        async with AsyncSessionLocal() as session:
            user = await session.get(User, user_id)
            if user is not None:
                await session.delete(user)
                await session.commit()
        revoke_all_sessions(username)
        await mu_settings.save_settings(enabled=original_enabled)
        await _restore_admin_state(snapshot)


@pytest.mark.asyncio
async def test_admin_session_can_reach_admin_endpoints():
    """管理员会话应能正常访问管理接口。"""
    from backend.database import init_db
    from backend.modules.auth.router import save_credentials
    from backend.modules.auth.utils import create_session, hash_password, revoke_all_sessions
    from backend.modules.multiuser.bootstrap import ensure_admin_user, get_admin_user

    await init_db()
    snapshot = await _snapshot_admin_state()

    admin_username = f"{TEST_USERNAME_PREFIX}admin"
    try:
        await save_credentials(admin_username, hash_password(TEST_PASSWORD))
        await ensure_admin_user()

        admin = await get_admin_user()
        assert admin is not None

        token = create_session(admin.username, user_id=admin.id)
        response = _client().get(
            "/api/admin/users",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert "items" in response.json()
        assert any(item["username"] == admin.username for item in response.json()["items"])
    finally:
        revoke_all_sessions(admin_username)
        await _restore_admin_state(snapshot)


@pytest.mark.asyncio
async def test_pending_user_session_is_rejected():
    """待审批用户的 token 不能通过鉴权解析。"""
    from backend.database import AsyncSessionLocal, init_db
    from backend.models.user import User
    from backend.modules.auth.utils import create_session, hash_password, revoke_all_sessions
    from backend.modules.multiuser.identity import resolve_session_user

    await init_db()

    from backend.modules.multiuser import settings as mu_settings

    original_enabled = (await mu_settings.load_settings(use_cache=False)).enabled
    await mu_settings.save_settings(enabled=True)

    user_id = str(uuid.uuid4())
    username = f"{TEST_USERNAME_PREFIX}pending_{user_id[:6]}"

    try:
        async with AsyncSessionLocal() as session:
            session.add(
                User(
                    id=user_id,
                    username=username,
                    password_hash=hash_password(TEST_PASSWORD),
                    role="user",
                    status="pending",
                )
            )
            await session.commit()

        token = create_session(username, user_id=user_id)
        assert await resolve_session_user(token, require_active=True) is None

        resolved_any = await resolve_session_user(token, require_active=False)
        assert resolved_any is not None and resolved_any.status == "pending"
    finally:
        async with AsyncSessionLocal() as session:
            user = await session.get(User, user_id)
            if user is not None:
                await session.delete(user)
                await session.commit()
        revoke_all_sessions(username)
        await mu_settings.save_settings(enabled=original_enabled)


def test_chat_mode_policy_limits_regular_user():
    """普通用户的可用模式由策略决定，管理员不受限制。"""
    from backend.modules.multiuser.identity import (
        allowed_chat_modes,
        resolve_chat_mode_for_user,
    )

    user = AuthUser(
        id="u-1",
        username="alice",
        role="user",
        status="active",
        chat_mode_policy="chat",
    )
    assert allowed_chat_modes(user) == ["chat"]
    assert resolve_chat_mode_for_user(user, "agent") == "chat"

    admin = AuthUser(
        id="a-1",
        username="root",
        role="admin",
        status="active",
        chat_mode_policy="chat",
    )
    assert allowed_chat_modes(admin) == ["agent", "chat"]
    assert resolve_chat_mode_for_user(admin, "chat") == "chat"
