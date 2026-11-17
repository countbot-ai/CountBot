"""多用户隔离测试：越权访问返回 403/404，密钥与凭证不外泄。"""

import uuid

import pytest
import pytest_asyncio


TEST_PASSWORD = "test-placeholder"
PREFIX = "__iso_test_"


@pytest_asyncio.fixture(autouse=True)
async def _ensure_auth_configured():
    """临时写入管理员密码哈希并开启多用户，测试后还原。"""
    from backend.modules.auth.router import get_stored_credentials, save_credentials
    from backend.modules.auth.utils import hash_password
    from backend.modules.multiuser import settings as mu_settings

    original_username, original_hash = await get_stored_credentials()
    if not original_hash:
        await save_credentials("__iso_admin__", hash_password(TEST_PASSWORD))
    original_enabled = (await mu_settings.load_settings(use_cache=False)).enabled
    await mu_settings.save_settings(enabled=True)
    try:
        yield
    finally:
        await mu_settings.save_settings(enabled=original_enabled)
        if not original_hash:
            await save_credentials(original_username, original_hash)


def _client():
    from fastapi.testclient import TestClient

    from backend.app import app

    return TestClient(app)


async def _create_user(role: str = "user", status: str = "active"):
    from backend.database import AsyncSessionLocal
    from backend.models.user import User
    from backend.modules.auth.utils import hash_password

    user_id = str(uuid.uuid4())
    username = f"{PREFIX}{user_id[:8]}"
    async with AsyncSessionLocal() as session:
        session.add(
            User(
                id=user_id,
                username=username,
                password_hash=hash_password(TEST_PASSWORD),
                role=role,
                status=status,
            )
        )
        await session.commit()
    return user_id, username


async def _token(user_id: str, username: str) -> str:
    from backend.modules.auth.utils import create_session

    return create_session(username, user_id=user_id)


async def _cleanup_user(user_id: str, username: str) -> None:
    from backend.database import AsyncSessionLocal
    from backend.models.user import User
    from backend.modules.auth.utils import revoke_all_sessions, revoke_sessions_for_user_id

    async with AsyncSessionLocal() as session:
        user = await session.get(User, user_id)
        if user is not None:
            await session.delete(user)
            await session.commit()
    revoke_sessions_for_user_id(user_id)
    revoke_all_sessions(username)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.asyncio
async def test_admin_endpoints_reject_regular_user():
    """普通用户不能触达管理员域接口，且响应不含任何密钥。"""
    from backend.database import init_db
    from backend.modules.multiuser.settings import invalidate_cache

    await init_db()
    invalidate_cache()
    user_id, username = await _create_user()
    try:
        token = await _token(user_id, username)
        client = _client()
        headers = {"Authorization": f"Bearer {token}"}

        for path in (
            "/api/settings",
            "/api/mcp/overview",
            "/api/system/info",
            "/api/queue/stats",
        ):
            response = client.get(path, headers=headers)
            assert response.status_code == 403, f"{path} -> {response.status_code}"
            body = response.text
            assert "sk-" not in body
    finally:
        await _cleanup_user(user_id, username)


@pytest.mark.asyncio
async def test_sessions_are_isolated_between_users():
    """A 的会话对 B 不可见、不可按 ID 访问。"""
    from backend.database import init_db
    from backend.modules.session.manager import SessionManager
    from backend.database import AsyncSessionLocal
    from backend.modules.multiuser.settings import invalidate_cache

    await init_db()
    invalidate_cache()
    a_id, a_name = await _create_user()
    b_id, b_name = await _create_user()
    a_session_id = None
    try:
        async with AsyncSessionLocal() as db:
            manager = SessionManager(db, owner_id=a_id)
            session = await manager.create_session("owned-by-a")
            a_session_id = session.id

        b_token = await _token(b_id, b_name)
        client = _client()
        headers = {"Authorization": f"Bearer {b_token}"}

        listing = client.get("/api/chat/sessions", headers=headers)
        assert listing.status_code == 200
        assert all(item["id"] != a_session_id for item in listing.json())

        detail = client.get(f"/api/chat/sessions/{a_session_id}", headers=headers)
        assert detail.status_code == 404

        messages = client.get(f"/api/chat/sessions/{a_session_id}/messages", headers=headers)
        assert messages.status_code == 404
    finally:
        async with AsyncSessionLocal() as db:
            manager = SessionManager(db)
            if a_session_id:
                await manager.delete_session(a_session_id)
        await _cleanup_user(a_id, a_name)
        await _cleanup_user(b_id, b_name)


@pytest.mark.asyncio
async def test_cron_jobs_are_isolated_between_users():
    """A 的定时任务对 B 不可见。"""
    from backend.database import AsyncSessionLocal, init_db
    from backend.modules.cron.service import CronService
    from backend.modules.multiuser.settings import invalidate_cache

    await init_db()
    invalidate_cache()
    a_id, a_name = await _create_user()
    b_id, b_name = await _create_user()
    job_id = None
    try:
        async with AsyncSessionLocal() as db:
            service = CronService(db, owner_id=a_id)
            job = await service.add_job(name="owned-by-a", schedule="0 * * * *", message="hello")
            job_id = job.id

        b_token = await _token(b_id, b_name)
        client = _client()
        headers = {"Authorization": f"Bearer {b_token}"}

        listing = client.get("/api/cron/jobs", headers=headers)
        assert listing.status_code == 200
        assert all(item["id"] != job_id for item in listing.json()["jobs"])

        detail = client.get(f"/api/cron/jobs/{job_id}", headers=headers)
        assert detail.status_code == 404

        updated = client.put(
            f"/api/cron/jobs/{job_id}",
            headers=headers,
            json={"name": "hijack"},
        )
        assert updated.status_code == 404

        deleted = client.delete(f"/api/cron/jobs/{job_id}", headers=headers)
        assert deleted.status_code == 404

        async with AsyncSessionLocal() as db:
            from backend.models.cron_job import CronJob

            assert await db.get(CronJob, job_id) is not None
    finally:
        async with AsyncSessionLocal() as session:
            if job_id:
                from backend.models.cron_job import CronJob

                job = await session.get(CronJob, job_id)
                if job is not None:
                    await session.delete(job)
                    await session.commit()
        await _cleanup_user(a_id, a_name)
        await _cleanup_user(b_id, b_name)


@pytest.mark.asyncio
async def test_me_models_hides_keys():
    """/api/me/models 只返回别名与可用性，不包含密钥字段。"""
    from backend.database import init_db
    from backend.modules.multiuser.settings import invalidate_cache

    await init_db()
    invalidate_cache()
    user_id, username = await _create_user()
    try:
        token = await _token(user_id, username)
        client = _client()
        response = client.get("/api/me/models", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        payload = response.json()
        assert "shared" in payload and "own" in payload
        text = response.text
        assert "api_key" not in text
        assert "api_base" not in text
    finally:
        await _cleanup_user(user_id, username)




@pytest.mark.asyncio
async def test_registration_closed_by_default():
    """默认不允许注册。"""
    from backend.database import init_db
    from backend.modules.multiuser.settings import invalidate_cache, load_settings

    await init_db()
    invalidate_cache()
    settings = await load_settings(use_cache=False)
    if settings.registration_allowed:
        pytest.skip("当前库已显式开启注册，跳过默认值断言")

    client = _client()
    response = client.post(
        "/api/auth/register",
        json={"username": f"{PREFIX}reg_{uuid.uuid4().hex[:6]}", "password": TEST_PASSWORD},
    )
    assert response.status_code == 403
    assert response.json().get("code") == "REGISTRATION_CLOSED"


@pytest.mark.asyncio
async def test_regular_user_cannot_read_admin_workspace_file():
    """工作区文件接口按用户解析，普通用户读不到管理员目录。"""
    from backend.database import init_db
    from backend.modules.multiuser.settings import invalidate_cache

    await init_db()
    invalidate_cache()
    user_id, username = await _create_user()
    try:
        token = await _token(user_id, username)
        client = _client()
        response = client.get(
            "/api/chat/workspace/README.md",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code in (403, 404)
    finally:
        await _cleanup_user(user_id, username)


@pytest.mark.asyncio
async def test_persona_partial_update_keeps_other_fields():
    """人设局部更新不得清掉未提交的字段。"""
    from backend.database import init_db
    from backend.modules.multiuser.settings import invalidate_cache

    await init_db()
    invalidate_cache()
    user_id, username = await _create_user()
    try:
        token = await _token(user_id, username)
        headers = {"Authorization": f"Bearer {token}"}
        client = _client()

        first = client.put(
            "/api/me/persona",
            json={"ai_name": "甲", "max_history_messages": 20},
            headers=headers,
        )
        assert first.status_code == 200, first.text

        # 只改语言，其余字段应保持第一次写入的值
        second = client.put(
            "/api/me/persona",
            json={"output_language": "English"},
            headers=headers,
        )
        assert second.status_code == 200, second.text

        payload = client.get("/api/me/persona", headers=headers).json()
        assert payload["ai_name"] == "甲"
        assert payload["max_history_messages"] == 20
        assert payload["output_language"] == "English"
    finally:
        await _cleanup_user(user_id, username)


@pytest.mark.asyncio
async def test_persona_update_accepts_full_form_fields():
    """表单里能编辑的项都必须被接受，否则保存等于没生效。"""
    from backend.database import init_db
    from backend.modules.multiuser.settings import invalidate_cache

    await init_db()
    invalidate_cache()
    user_id, username = await _create_user()
    try:
        token = await _token(user_id, username)
        headers = {"Authorization": f"Bearer {token}"}
        response = _client().put(
            "/api/me/persona",
            json={
                "max_history_messages": 12,
                "enable_short_context_summary": True,
            },
            headers=headers,
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["max_history_messages"] == 12
        assert payload["enable_short_context_summary"] is True
    finally:
        await _cleanup_user(user_id, username)


async def _create_session(owner_id: str) -> str:
    from backend.database import AsyncSessionLocal
    from backend.models.session import Session

    session_id = f"__iso_sess_{uuid.uuid4().hex[:10]}"
    async with AsyncSessionLocal() as session:
        session.add(Session(id=session_id, name="iso", owner_id=owner_id))
        await session.commit()
    return session_id


async def _drop_session(session_id: str) -> None:
    from backend.database import AsyncSessionLocal
    from backend.models.session import Session

    async with AsyncSessionLocal() as session:
        row = await session.get(Session, session_id)
        if row is not None:
            await session.delete(row)
            await session.commit()


@pytest.mark.asyncio
async def test_queue_cancel_requires_ownership():
    """停止生成对普通用户开放，但只能取消自己的会话。"""
    from backend.database import init_db
    from backend.modules.multiuser.settings import invalidate_cache

    await init_db()
    invalidate_cache()
    a_id, a_name = await _create_user()
    b_id, b_name = await _create_user()
    own_session = await _create_session(a_id)
    other_session = await _create_session(b_id)
    try:
        token = await _token(a_id, a_name)
        headers = {"Authorization": f"Bearer {token}"}
        client = _client()

        own = client.post(
            "/api/queue/cancel", json={"session_id": own_session}, headers=headers
        )
        assert own.status_code == 200, own.text

        other = client.post(
            "/api/queue/cancel", json={"session_id": other_session}, headers=headers
        )
        assert other.status_code == 404, other.text

        # 不存在的会话与「别人的会话」返回一致，避免状态码成为存在性探测口
        missing = client.post(
            "/api/queue/cancel", json={"session_id": "no-such-session"}, headers=headers
        )
        assert missing.status_code == 404, missing.text
    finally:
        await _drop_session(own_session)
        await _drop_session(other_session)
        await _cleanup_user(a_id, a_name)
        await _cleanup_user(b_id, b_name)


@pytest.mark.asyncio
async def test_queue_stats_stays_admin_only():
    """队列统计是全局视角，普通用户仍不可见。"""
    from backend.database import init_db
    from backend.modules.multiuser.settings import invalidate_cache

    await init_db()
    invalidate_cache()
    user_id, username = await _create_user()
    try:
        token = await _token(user_id, username)
        response = _client().get(
            "/api/queue/stats", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 403
    finally:
        await _cleanup_user(user_id, username)






@pytest.mark.asyncio
async def test_publish_shared_skill_requires_admin():
    """共享是管理员能力：普通用户的技能始终私有，不能发布给他人。"""
    from backend.database import init_db
    from backend.modules.multiuser.settings import invalidate_cache

    await init_db()
    invalidate_cache()
    user_id, username = await _create_user()
    try:
        token = await _token(user_id, username)
        response = _client().post(
            "/api/shared-skills/publish",
            json={"name": "my-skill", "audience": None},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403
    finally:
        await _cleanup_user(user_id, username)


@pytest.mark.asyncio
async def test_regular_user_cannot_edit_builtin_personality():
    """内置性格对所有用户共享，普通用户只能读、不能改。"""
    from backend.database import AsyncSessionLocal, init_db
    from backend.models.personality import Personality
    from backend.modules.multiuser.settings import invalidate_cache

    await init_db()
    invalidate_cache()
    builtin_id = f"__builtin_{uuid.uuid4().hex[:8]}"
    user_id, username = await _create_user()
    try:
        async with AsyncSessionLocal() as session:
            session.add(
                Personality(
                    id=builtin_id,
                    name="内置性格",
                    description="原始描述",
                    traits=["稳定"],
                    speaking_style="简洁",
                    icon="Smile",
                    is_builtin=True,
                )
            )
            await session.commit()

        token = await _token(user_id, username)
        response = _client().put(
            f"/api/personalities/{builtin_id}",
            json={"name": "被篡改"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404

        async with AsyncSessionLocal() as session:
            row = await session.get(Personality, builtin_id)
            assert row is not None and row.name == "内置性格"
    finally:
        async with AsyncSessionLocal() as session:
            row = await session.get(Personality, builtin_id)
            if row is not None:
                await session.delete(row)
                await session.commit()
        await _cleanup_user(user_id, username)


@pytest.mark.asyncio
async def test_regular_user_login_rejected_when_multiuser_disabled():
    """关闭多用户后，普通账号不能再登录或继续使用。"""
    from backend.database import init_db
    from backend.modules.multiuser import settings as mu_settings

    await init_db()
    user_id, username = await _create_user()
    try:
        await mu_settings.save_settings(enabled=False)
        response = _client().post(
            "/api/auth/login",
            json={"username": username, "password": TEST_PASSWORD},
        )
        assert response.status_code == 403
        assert response.json().get("code") == "MULTIUSER_DISABLED"
    finally:
        await mu_settings.save_settings(enabled=True)
        await _cleanup_user(user_id, username)


@pytest.mark.asyncio
async def test_me_reports_chat_mode_policy():
    """/api/me 返回用户可用模式，前端据此隐藏模式切换。"""
    from backend.database import AsyncSessionLocal, init_db
    from backend.models.user import User

    await init_db()
    user_id, username = await _create_user()
    try:
        async with AsyncSessionLocal() as session:
            row = await session.get(User, user_id)
            assert row is not None
            row.chat_mode_policy = "chat"
            await session.commit()

        response = _client().get(
            "/api/me",
            headers={"Authorization": f"Bearer {await _token(user_id, username)}"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["chat_mode_policy"] == "chat"
        assert payload["allowed_chat_modes"] == ["chat"]
    finally:
        await _cleanup_user(user_id, username)


@pytest.mark.asyncio
async def test_agent_teams_are_isolated_per_user():
    """每个用户只能看到、修改和调用自己创建的团队，管理员也看不到用户团队。"""
    from backend.database import AsyncSessionLocal, init_db
    from backend.models.agent_team import AgentTeam

    await init_db()
    user_a, name_a = await _create_user()
    user_b, name_b = await _create_user()
    admin_id, admin_name = await _create_user(role="admin")
    try:
        headers_a = {"Authorization": f"Bearer {await _token(user_a, name_a)}"}
        headers_b = {"Authorization": f"Bearer {await _token(user_b, name_b)}"}
        headers_admin = {"Authorization": f"Bearer {await _token(admin_id, admin_name)}"}
        payload = {"name": "iso-team", "mode": "pipeline", "agents": []}

        created_a = _client().post("/api/agent-teams/", json=payload, headers=headers_a)
        created_b = _client().post("/api/agent-teams/", json=payload, headers=headers_b)
        assert created_a.status_code == 201
        assert created_b.status_code == 201
        team_b_id = created_b.json()["id"]

        # 各自列表只包含自己的同名团队
        list_a = _client().get("/api/agent-teams/", headers=headers_a).json()
        list_b = _client().get("/api/agent-teams/", headers=headers_b).json()
        assert [item["name"] for item in list_a] == ["iso-team"]
        assert [item["name"] for item in list_b] == ["iso-team"]

        # 跨用户读取、修改、删除一律 404
        assert _client().get(f"/api/agent-teams/{team_b_id}", headers=headers_a).status_code == 404
        assert _client().put(
            f"/api/agent-teams/{team_b_id}",
            json={"name": "hijacked"},
            headers=headers_a,
        ).status_code == 404
        assert _client().delete(f"/api/agent-teams/{team_b_id}", headers=headers_a).status_code == 404

        # 管理员列表只含 owner_id 为空的团队，不含普通用户的团队
        admin_teams = _client().get("/api/agent-teams/", headers=headers_admin).json()
        assert all(item["name"] != "iso-team" for item in admin_teams)
    finally:
        from sqlalchemy import delete

        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(AgentTeam).where(AgentTeam.owner_id.in_([user_a, user_b]))
            )
            await session.commit()
        await _cleanup_user(user_a, name_a)
        await _cleanup_user(user_b, name_b)
        await _cleanup_user(admin_id, admin_name)


@pytest.mark.asyncio
async def test_team_model_config_is_admin_only():
    """普通用户的团队沿用当前对话模型，不能单独写入团队模型配置。"""
    from backend.database import AsyncSessionLocal, init_db
    from backend.models.agent_team import AgentTeam
    from sqlalchemy import delete

    await init_db()
    user_id, username = await _create_user()
    try:
        headers = {"Authorization": f"Bearer {await _token(user_id, username)}"}
        created = _client().post(
            "/api/agent-teams/",
            json={"name": "iso-model-team", "mode": "pipeline", "agents": []},
            headers=headers,
        )
        assert created.status_code == 201
        team_id = created.json()["id"]

        response = _client().put(
            f"/api/agent-teams/{team_id}/config",
            json={"provider": "custom_openai", "model": "admin-only-model"},
            headers=headers,
        )
        assert response.status_code == 403

        config = _client().get(f"/api/agent-teams/{team_id}/config", headers=headers)
        assert config.status_code == 200
        assert config.json()["use_custom_model"] is False
        assert config.json()["model_settings"]["api_key"] == ""
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(delete(AgentTeam).where(AgentTeam.owner_id == user_id))
            await session.commit()
        await _cleanup_user(user_id, username)


def _telegram_config():
    from backend.modules.config.schema import TelegramAccountConfig, TelegramConfig

    return TelegramConfig(
        enabled=True,
        token="admin-token",
        account_id="default",
        accounts={
            "u_a": TelegramAccountConfig(
                account_id="u_a", token="a-token", enabled=True, owner_id="a"
            ),
            "u_b": TelegramAccountConfig(
                account_id="u_b", token="b-token", enabled=True, owner_id="b"
            ),
        },
    )


def test_channel_view_is_scoped_by_owner():
    """普通用户只能看到自己的机器人，管理员视图不包含用户账号。"""
    from backend.api.channels import _channel_view_for_owner

    config = _telegram_config()
    view_a = _channel_view_for_owner(config, "a")
    assert view_a.account_id == "u_a"
    assert view_a.token == "a-token"
    assert "u_b" not in view_a.accounts
    assert "admin-token" not in view_a.model_dump_json()

    admin_view = _channel_view_for_owner(config, None)
    assert admin_view.token == "admin-token"
    assert "u_a" not in admin_view.accounts
    assert "u_b" not in admin_view.accounts


def test_channel_merge_preserves_other_owners():
    """一个用户保存渠道时，不覆盖管理员和其他用户的账号。"""
    from backend.api.channels import _merge_owned_channel_config
    from backend.modules.config.schema import TelegramConfig

    merged = _merge_owned_channel_config(
        _telegram_config(),
        {
            "account_id": "u_a2",
            "token": "a2-token",
            "enabled": True,
            "accounts": {},
        },
        "a",
        TelegramConfig,
    )
    assert merged.account_id == "default"
    assert merged.token == "admin-token"
    assert merged.accounts["u_a2"].owner_id == "a"
    assert "u_a" not in merged.accounts
    assert "u_b" in merged.accounts


def test_channel_merge_namespaces_conflicting_account_id():
    """普通用户不能占用管理员主账号 ID。"""
    from backend.api.channels import _merge_owned_channel_config
    from backend.modules.config.schema import TelegramConfig

    merged = _merge_owned_channel_config(
        _telegram_config(),
        {"account_id": "default", "token": "user-token", "enabled": True, "accounts": {}},
        "a",
        TelegramConfig,
    )
    assert "default" not in merged.accounts
    assert merged.accounts["u_a_default"].token == "user-token"


def test_resolve_channel_account_owner(monkeypatch):
    """入站消息按渠道账号归属路由。"""
    from backend.modules.channels import handler_router
    from backend.modules.config.schema import AppConfig

    config = AppConfig()
    config.channels.telegram = _telegram_config()
    monkeypatch.setattr(handler_router.config_loader, "config", config)

    assert handler_router.resolve_account_owner("telegram", "default") is None
    assert handler_router.resolve_account_owner("telegram", "u_a") == "a"
    assert handler_router.resolve_account_owner("telegram", "missing") is None


@pytest.mark.asyncio
async def test_cron_channel_push_rejects_other_owner(monkeypatch):
    """普通用户的定时任务只能推送到自己的账号与会话。"""
    from types import SimpleNamespace

    from fastapi import HTTPException

    from backend.api.cron._common import validate_channel_push_for_user
    from backend.modules.config import loader as config_module
    from backend.modules.multiuser.identity import AuthUser

    monkeypatch.setattr(
        config_module.config_loader,
        "config",
        SimpleNamespace(channels=SimpleNamespace(telegram=object())),
    )
    monkeypatch.setattr(
        "backend.api.channels._owned_account_ids",
        lambda channel_config, owner_id: {"u_a1"},
    )

    async def _fake_chats(channel_ids, owner_id=None, **_):
        assert owner_id == "a"
        return {"telegram": [{"chat_id": "chat-a", "account_id": "u_a1"}]}

    monkeypatch.setattr("backend.api.channels._collect_channel_chats", _fake_chats)

    user = AuthUser(id="a", username="a", role="user")
    own_request = SimpleNamespace(channel="telegram", account_id="u_a1", chat_id="chat-a", deliver_response=True)
    await validate_channel_push_for_user(user, own_request)

    with pytest.raises(HTTPException) as exc:
        await validate_channel_push_for_user(
            user,
            SimpleNamespace(channel="telegram", account_id="default", chat_id="chat-a", deliver_response=True),
        )
    assert exc.value.status_code == 403

    with pytest.raises(HTTPException) as exc:
        await validate_channel_push_for_user(
            user,
            SimpleNamespace(channel="telegram", account_id="u_a1", chat_id="admin-chat", deliver_response=True),
        )
    assert exc.value.status_code == 400

    admin = AuthUser(id="admin", username="admin", role="admin")
    await validate_channel_push_for_user(
        admin,
        SimpleNamespace(channel="telegram", account_id="default", chat_id="admin-chat", deliver_response=True),
    )


@pytest.mark.asyncio
async def test_cron_model_rejects_unavailable_model(monkeypatch):
    """普通用户的定时任务模型必须在其可用清单内。"""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from fastapi import HTTPException

    from backend.api.cron._common import validate_model_for_user
    from backend.modules.multiuser.effective import ModelResolutionError
    from backend.modules.multiuser.identity import AuthUser

    user = AuthUser(id="a", username="a", role="user")
    await validate_model_for_user(
        user, SimpleNamespace(model_provider=None, model_name=None)
    )

    with pytest.raises(HTTPException) as exc:
        await validate_model_for_user(
            user, SimpleNamespace(model_provider="openai", model_name="")
        )
    assert exc.value.status_code == 400

    monkeypatch.setattr(
        "backend.modules.multiuser.effective.resolve_model_ref_for_user",
        AsyncMock(side_effect=ModelResolutionError("模型不可用或未共享给你")),
    )
    with pytest.raises(HTTPException) as exc:
        await validate_model_for_user(
            user, SimpleNamespace(model_provider="openai", model_name="gpt-4o")
        )
    assert exc.value.status_code == 400

    admin = AuthUser(id="admin", username="admin", role="admin")
    await validate_model_for_user(
        admin, SimpleNamespace(model_provider="openai", model_name="gpt-4o")
    )


@pytest.mark.asyncio
async def test_cron_execution_sessions_are_owned_and_isolated(monkeypatch):
    """普通用户任务使用独立会话，且会话归属该用户。"""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from backend.database import AsyncSessionLocal, init_db
    from backend.models.session import Session
    from backend.modules.cron.executor import CronExecutor

    await init_db()
    owner = "__cron_owner__"

    class _FakeAgent:
        tools = None

        def __init__(self):
            self.seen: list[str] = []

        async def process_direct(self, **kwargs):
            self.seen.append(kwargs["session_id"])
            return "ok"

    agent = _FakeAgent()
    executor = CronExecutor(agent=agent, bus=None)
    monkeypatch.setattr(
        executor,
        "_resolve_agent",
        AsyncMock(return_value=(agent, owner, SimpleNamespace(username="a", owner_id=owner))),
    )
    monkeypatch.setattr(executor, "_build_user_model_override", AsyncMock(return_value=None))
    monkeypatch.setattr(executor, "_deliver_user_notification", AsyncMock())

    created: set[str] = set()
    try:
        await executor.execute("job-a", "hello")
        await executor.execute("job-a", "hello")
        assert agent.seen[0] != agent.seen[1]
        assert all(session_id.startswith("cron:job-a:") for session_id in agent.seen)

        await executor.execute("job-a", "hello", link_context=True)
        await executor.execute("job-a", "hello", link_context=True)
        assert agent.seen[2] == agent.seen[3] == "cron:job-a"

        created = set(agent.seen)
        async with AsyncSessionLocal() as db:
            for session_id in created:
                row = await db.get(Session, session_id)
                assert row is not None
                assert row.owner_id == owner
    finally:
        async with AsyncSessionLocal() as db:
            for session_id in set(agent.seen):
                row = await db.get(Session, session_id)
                if row is not None:
                    await db.delete(row)
            await db.commit()


@pytest.mark.asyncio
async def test_cron_session_refuses_other_owner():
    """会话已归属他人时必须失败，不能改写归属。"""
    from backend.database import AsyncSessionLocal, init_db
    from backend.models.session import Session
    from backend.modules.cron.executor import CronExecutor

    await init_db()
    session_id = "cron:__owner_guard__"
    async with AsyncSessionLocal() as db:
        db.add(Session(id=session_id, name=session_id, owner_id="user-b"))
        await db.commit()

    executor = CronExecutor(agent=None, bus=None)
    try:
        with pytest.raises(RuntimeError):
            await executor._ensure_owned_session(session_id, "user-a")
        async with AsyncSessionLocal() as db:
            row = await db.get(Session, session_id)
            assert row is not None and row.owner_id == "user-b"
    finally:
        async with AsyncSessionLocal() as db:
            row = await db.get(Session, session_id)
            if row is not None:
                await db.delete(row)
                await db.commit()
