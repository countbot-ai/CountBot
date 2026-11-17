"""普通用户运行时边界回归：模型解析、WS 覆盖、身份与工作区隔离。"""

import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.modules.multiuser.identity import AuthUser


TEST_PASSWORD = "test-placeholder"
PREFIX = "__boundary_test_"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture(autouse=True)
async def _ensure_auth_configured():
    """RemoteAuthMiddleware 在管理员未初始化时会拦截所有请求。"""
    from backend.modules.auth.router import get_stored_credentials, save_credentials
    from backend.modules.auth.utils import hash_password

    original_username, original_hash = await get_stored_credentials()
    if not original_hash:
        await save_credentials("__boundary_admin__", hash_password(TEST_PASSWORD))
    try:
        yield
    finally:
        if not original_hash:
            await save_credentials(original_username, original_hash)


def _regular_user(owner_id: str = "u-regular"):
    return SimpleNamespace(
        id=owner_id,
        owner_id=owner_id,
        username="regular",
        is_admin=False,
    )


# ---------------------------------------------------------------------------
# 共享模型：首次运行时自动选定
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_first_runtime_auto_selects_visible_shared_model(monkeypatch):
    from backend.modules.multiuser import effective
    from backend.modules.multiuser import settings as mu_settings

    async def _fake_settings(use_cache=True):
        return SimpleNamespace(mode="shared", shared_providers=True)

    async def _fake_available(user):
        return {
            "shared": [
                {
                    "source": "shared",
                    "provider": "admin-provider",
                    "model": "shared-model",
                    "alias": "共享模型",
                }
            ],
            "own": [],
            "selected": None,
            "mode": "shared",
            "shared_enabled": True,
        }

    async def _fake_load(_user_id):
        return {}

    captured = {}

    async def _fake_patch(user_id, **changes):
        captured.update(changes)
        captured["user_id"] = user_id
        return changes

    def _fake_from_shared(provider, model):
        return effective.ResolvedModel("shared", provider, model, "共享模型", object())

    monkeypatch.setattr(mu_settings, "load_settings", _fake_settings)
    monkeypatch.setattr(effective, "list_available_models", _fake_available)
    monkeypatch.setattr(effective, "load_user_config", _fake_load)
    monkeypatch.setattr(effective, "patch_user_config", _fake_patch)
    monkeypatch.setattr(effective, "_from_shared", _fake_from_shared)

    resolved = await effective.resolve_model_for_user(_regular_user())

    assert resolved.provider_id == "admin-provider"
    assert resolved.model_id == "shared-model"
    assert captured["user_id"] == "u-regular"
    assert captured["model_ref"] == {
        "source": "shared",
        "provider": "admin-provider",
        "model": "shared-model",
        "alias": "共享模型",
    }


@pytest.mark.asyncio
async def test_no_visible_model_still_reports_actionable_error(monkeypatch):
    from backend.modules.multiuser import effective
    from backend.modules.multiuser import settings as mu_settings

    async def _fake_settings(use_cache=True):
        return SimpleNamespace(mode="shared", shared_providers=True)

    async def _fake_available(user):
        return {"shared": [], "own": [], "selected": None, "mode": "shared", "shared_enabled": True}

    async def _unexpected_patch(*_args, **_kwargs):
        raise AssertionError("无可用模型时不应写入 model_ref")

    monkeypatch.setattr(mu_settings, "load_settings", _fake_settings)
    monkeypatch.setattr(effective, "list_available_models", _fake_available)
    monkeypatch.setattr(effective, "load_user_config", lambda uid: _empty_config(uid))
    monkeypatch.setattr(effective, "patch_user_config", _unexpected_patch)

    with pytest.raises(effective.ModelResolutionError, match="尚未选择可用模型"):
        await effective.resolve_model_for_user(_regular_user())


async def _empty_config(_user_id):
    return {}


@pytest.mark.asyncio
async def test_admin_model_resolution_is_unchanged(monkeypatch):
    from backend.modules.config import loader as loader_module
    from backend.modules.multiuser import effective

    provider = object()
    cfg = SimpleNamespace(
        model=SimpleNamespace(provider="global-p", model="global-m"),
        providers={"global-p": provider},
    )
    monkeypatch.setattr(loader_module.config_loader, "config", cfg, raising=False)

    resolved = await effective.resolve_model_for_user(
        AuthUser(id="admin", username="admin", role="admin")
    )
    assert resolved.provider_id == "global-p"
    assert resolved.model_id == "global-m"
    assert resolved.provider_config is provider


# ---------------------------------------------------------------------------
# WebSocket：普通用户不使用管理员的会话级模型覆盖
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ws_runtime_skips_global_override_for_regular_user(monkeypatch):
    """普通用户：生成参数覆盖生效，provider/model/密钥/地址不得被会话覆盖。"""
    from backend.ws import events

    def _unexpected_runtime_state(*_args, **_kwargs):
        raise AssertionError("普通用户不应读取管理员 provider 的运行时状态")

    captured: dict = {}

    def _fake_override(runtime_config, force=False):
        captured["force"] = force
        return {"provider": "admin-p", "model": "admin-m", "temperature": 0.5}

    monkeypatch.setattr(events, "get_provider_runtime_state", _unexpected_runtime_state)
    monkeypatch.setattr(events, "build_session_model_override", _fake_override)

    provider = object()
    agent_loop = SimpleNamespace(provider=provider)
    session = SimpleNamespace(use_custom_config=False)

    result = await events._resolve_ws_runtime(
        agent_loop, "s1", session, SimpleNamespace(), user=_regular_user()
    )
    assert result == ({"temperature": 0.5}, None, provider)
    assert captured["force"] is False


@pytest.mark.asyncio
async def test_ws_persona_override_applies_session_custom_prompt_for_regular_user():
    """普通用户在会话里改的自定义系统提示词要生效，且基底仍是自己的用户人设。"""
    from backend.modules.config.schema import PersonaConfig
    from backend.ws import events

    base_persona = PersonaConfig(ai_name="小C", user_name="主人")
    agent_loop = SimpleNamespace(
        provider=object(),
        context_builder=SimpleNamespace(persona_config=base_persona),
    )
    runtime_config = SimpleNamespace(
        has_custom_model_config=False,
        has_custom_persona_config=True,
        persona_overrides={"custom_personality": "用海盗口吻说话"},
    )
    session = SimpleNamespace(use_custom_config=True)

    _, persona_override, _ = await events._resolve_ws_runtime(
        agent_loop, "s1", session, runtime_config, user=_regular_user()
    )

    assert persona_override is not None
    assert persona_override.custom_personality == "用海盗口吻说话"
    # 用户人设字段保留，不继承管理员全局人设
    assert persona_override.ai_name == "小C"


@pytest.mark.asyncio
async def test_ws_persona_override_stays_none_without_session_persona():
    """会话没写人设时不能凭空造 persona 覆盖。"""
    from backend.modules.config.schema import PersonaConfig
    from backend.ws import events

    agent_loop = SimpleNamespace(
        provider=object(),
        context_builder=SimpleNamespace(persona_config=PersonaConfig()),
    )
    runtime_config = SimpleNamespace(
        has_custom_model_config=False,
        has_custom_persona_config=False,
        persona_overrides=None,
    )

    result = await events._resolve_ws_runtime(
        agent_loop, "s1", SimpleNamespace(use_custom_config=False),
        runtime_config, user=_regular_user(),
    )
    assert result == (None, None, agent_loop.provider)


@pytest.mark.asyncio
async def test_regular_user_cannot_read_or_export_admin_settings():
    """普通用户不得读取全局配置，也不得导出全局配置（含 api_key）。"""
    from fastapi.testclient import TestClient

    from backend.app import app
    from backend.database import AsyncSessionLocal, init_db
    from backend.models.user import User
    from backend.modules.auth.utils import (
        create_session,
        hash_password,
        revoke_all_sessions,
        revoke_sessions_for_user_id,
    )
    from backend.modules.multiuser import settings as mu_settings

    await init_db()
    original_enabled = (await mu_settings.load_settings(use_cache=False)).enabled
    await mu_settings.save_settings(enabled=True)

    user_id = str(uuid.uuid4())
    username = f"{PREFIX}{user_id[:8]}"
    try:
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
        client = TestClient(app)
        headers = {"Authorization": f"Bearer {token}"}

        for path in (
            "/api/settings",
            "/api/settings/export",
            "/api/settings/export?include_api_keys=true",
            "/api/settings/providers",
        ):
            assert client.get(path, headers=headers).status_code == 403, path
    finally:
        async with AsyncSessionLocal() as session:
            row = await session.get(User, user_id)
            if row is not None:
                await session.delete(row)
                await session.commit()
        revoke_sessions_for_user_id(user_id)
        revoke_all_sessions(username)
        await mu_settings.save_settings(enabled=original_enabled)


@pytest.mark.asyncio
async def test_multiuser_disables_local_admin_bypass(monkeypatch):
    """多用户开启时，本机回环请求不再免登录当管理员。"""
    from starlette.requests import Request

    from backend.modules.multiuser import permissions, settings as mu_settings

    monkeypatch.setattr(permissions, "_is_local_request", lambda request: True)
    request = Request({"type": "http", "method": "GET", "path": "/api/settings", "headers": []})

    original_enabled = (await mu_settings.load_settings(use_cache=False)).enabled
    try:
        await mu_settings.save_settings(enabled=True)
        assert await permissions.get_current_user(request) is None

        await mu_settings.save_settings(enabled=False)
        user = await permissions.get_current_user(request)
        assert user is not None and user.is_admin
    finally:
        await mu_settings.save_settings(enabled=original_enabled)


# ---------------------------------------------------------------------------
# 身份：显式会话优先于本机管理员旁路
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_explicit_session_beats_local_admin_bypass(monkeypatch):
    """loopback/隧道带普通用户 cookie 时不得被提升为管理员。"""
    from fastapi.testclient import TestClient

    from backend.app import app
    from backend.database import AsyncSessionLocal, init_db
    from backend.models.user import User
    from backend.modules.auth.utils import (
        create_session,
        hash_password,
        revoke_all_sessions,
        revoke_sessions_for_user_id,
    )
    from backend.modules.multiuser import permissions

    async def _fake_settings(use_cache=True):
        return SimpleNamespace(allow_local_admin_bypass=True)

    monkeypatch.setattr(permissions, "load_settings", _fake_settings)
    monkeypatch.setattr(permissions, "_is_local_request", lambda request: True)

    await init_db()
    from backend.modules.multiuser import settings as mu_settings

    original_enabled = (await mu_settings.load_settings(use_cache=False)).enabled
    await mu_settings.save_settings(enabled=True)

    user_id = str(uuid.uuid4())
    username = f"{PREFIX}{user_id[:8]}"
    try:
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
        client = TestClient(app)
        response = client.get(
            "/api/queue/stats", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 403
    finally:
        async with AsyncSessionLocal() as session:
            row = await session.get(User, user_id)
            if row is not None:
                await session.delete(row)
                await session.commit()
        revoke_sessions_for_user_id(user_id)
        revoke_all_sessions(username)
        await mu_settings.save_settings(enabled=original_enabled)


# ---------------------------------------------------------------------------
# 多用户默认策略与共享技能登记
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shared_skills_wiki_mcp_defaults_to_disabled(monkeypatch):
    from backend.modules.multiuser import settings as mu_settings

    async def _empty_raw():
        return {}

    monkeypatch.setattr(mu_settings, "_read_raw_settings", _empty_raw)
    settings = await mu_settings.load_settings(use_cache=False)
    assert settings.shared_skills_wiki_mcp is False


def test_shared_skill_mutations_invalidate_user_runtimes(monkeypatch):
    from backend.api import shared_skills as api
    from backend.modules.multiuser import runtime

    calls = []
    monkeypatch.setattr(
        runtime.user_runtime_manager, "invalidate_all", lambda: calls.append(True)
    )

    api._invalidate_shared_skill_runtimes()
    assert calls == [True]


def test_dotted_skill_version_name_is_publishable(tmp_path):
    """版本号形式的技能目录名是合法共享名；仅拒绝路径穿越式名字。"""
    from backend.modules.multiuser.shared_skills import SharedSkillError, validate_publishable

    skill = tmp_path / "humanizer-1.0.0"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "---\nname: humanizer-1.0.0\ndescription: 写作风格\n---\n正文\n",
        encoding="utf-8",
    )
    assert validate_publishable(skill, skill.name)["name"] == "humanizer-1.0.0"

    with pytest.raises(SharedSkillError):
        validate_publishable(skill, "a..b")


@pytest.mark.asyncio
async def test_publishable_list_includes_skills_with_scripts(tmp_path, monkeypatch):
    """共享按目录整体复制，脚本类技能也提供发布入口。"""
    from backend.api import shared_skills as api
    from backend.modules.multiuser import shared_skills as module

    root = tmp_path / "skills"
    clean = root / "clean-skill"
    clean.mkdir(parents=True)
    (clean / "SKILL.md").write_text(
        "---\nname: clean-skill\ndescription: 纯文本技能\n---\n正文\n", encoding="utf-8"
    )
    with_script = root / "with-script"
    with_script.mkdir(parents=True)
    (with_script / "SKILL.md").write_text(
        "---\nname: with-script\ndescription: 含脚本\n---\n正文\n", encoding="utf-8"
    )
    (with_script / "run.py").write_text("print('x')\n", encoding="utf-8")

    monkeypatch.setattr(module, "user_skills_dir", lambda user: root)
    names = await api.list_publishable_skills(
        AuthUser(id="admin", username="admin", role="admin")
    )
    assert names == ["clean-skill", "with-script"]


def test_approved_shared_skill_is_visible_to_regular_user():
    from backend.modules.multiuser.shared_skills import is_visible_to

    row = SimpleNamespace(
        status="approved",
        visibility="shared",
        owner_id="__system__",
        audience_json=None,
    )
    assert is_visible_to(row, _regular_user()) is True


@pytest.mark.asyncio
async def test_shared_skills_listing_is_available_to_regular_user():
    """普通用户能在设置页读到管理员发布的共享技能。"""
    from fastapi.testclient import TestClient

    from backend.app import app
    from backend.database import AsyncSessionLocal, init_db
    from backend.models.skill import (
        STATUS_APPROVED,
        VISIBILITY_SHARED,
        SkillRegistry,
        UserSkillState,
    )
    from backend.models.user import User
    from backend.modules.auth.utils import (
        create_session,
        hash_password,
        revoke_all_sessions,
        revoke_sessions_for_user_id,
    )

    await init_db()
    from backend.modules.multiuser import settings as mu_settings

    original_enabled = (await mu_settings.load_settings(use_cache=False)).enabled
    await mu_settings.save_settings(enabled=True)

    user_id = str(uuid.uuid4())
    username = f"{PREFIX}{user_id[:8]}"
    skill_id = f"__boundary_skill_{uuid.uuid4().hex[:8]}"
    try:
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
            session.add(
                SkillRegistry(
                    id=skill_id,
                    name="admin-shared-demo",
                    owner_id="__system__",
                    scope="user",
                    visibility=VISIBILITY_SHARED,
                    status=STATUS_APPROVED,
                    version=1,
                    storage_path="",
                    audience_json=None,
                )
            )
            await session.commit()

        token = create_session(username, user_id=user_id)
        client = TestClient(app)
        response = client.get(
            "/api/shared-skills", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        items = response.json()
        assert any(item["name"] == "admin-shared-demo" for item in items)
        assert all(item["audience"] is None for item in items)

        # 启停只影响自己；接口必须回显刚写入的状态，而不是默认 enabled=True
        disabled = client.put(
            f"/api/shared-skills/{skill_id}/state",
            json={"enabled": False},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert disabled.status_code == 200
        assert disabled.json()["enabled"] is False
        listed = client.get(
            "/api/shared-skills", headers={"Authorization": f"Bearer {token}"}
        )
        assert listed.json()[0]["enabled"] is False
    finally:
        from sqlalchemy import delete as sa_delete

        async with AsyncSessionLocal() as session:
            await session.execute(
                sa_delete(UserSkillState).where(
                    UserSkillState.user_id == user_id,
                    UserSkillState.skill_id == skill_id,
                )
            )
            for model, key in ((SkillRegistry, skill_id), (User, user_id)):
                row = await session.get(model, key)
                if row is not None:
                    await session.delete(row)
            await session.commit()
        revoke_sessions_for_user_id(user_id)
        revoke_all_sessions(username)
        await mu_settings.save_settings(enabled=original_enabled)


# ---------------------------------------------------------------------------
# 技能与工作区隔离
# ---------------------------------------------------------------------------


def test_reload_preserves_extra_disabled_skills(tmp_path):
    """热重载只重读配置文件时，会丢掉用户级共享技能的停用状态。"""
    from backend.modules.agent.skills import SkillsLoader

    ws = tmp_path / "workspace"
    skill = ws / "skills" / "team-skill"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: team-skill\n---\n正文\n", encoding="utf-8"
    )

    loader = SkillsLoader(
        ws / "skills",
        include_builtin=False,
        external_skills_dirs=[],
        extra_disabled_skills={"team-skill"},
    )
    assert loader.get_skill("team-skill").enabled is False
    loader.reload()
    assert loader.get_skill("team-skill").enabled is False


def test_bundled_copies_are_not_user_private_skills(tmp_path, monkeypatch):
    from backend.modules.agent.skills import SkillsLoader
    from backend.modules.workspace import seeding

    bundled = tmp_path / "app" / "workspace" / "skills"
    workspace = tmp_path / "users" / "u1" / "workspace"
    for name in ("pristine-copy", "edited-copy"):
        source = bundled / name
        source.mkdir(parents=True)
        (source / "SKILL.md").write_text(
            f"---\nname: {name}\n---\n原始\n", encoding="utf-8"
        )

    for name in ("pristine-copy", "edited-copy", "my-own"):
        target = workspace / "skills" / name
        target.mkdir(parents=True)
        body = "用户改写" if name == "edited-copy" else (
            "自定义" if name == "my-own" else "原始"
        )
        (target / "SKILL.md").write_text(
            f"---\nname: {name}\n---\n{body}\n", encoding="utf-8"
        )

    monkeypatch.setattr(seeding, "bundled_skills_dir", lambda: bundled)
    excluded = seeding.bundled_skill_copy_names(workspace)
    assert excluded == {"pristine-copy", "edited-copy"}

    loader = SkillsLoader(
        workspace / "skills",
        include_builtin=False,
        external_skills_dirs=[],
        excluded_workspace_skills=excluded,
    )
    assert {item["name"] for item in loader.list_skills()} == {"my-own"}


def test_user_workspace_seeding_skips_skills(tmp_path, monkeypatch):
    from backend.modules.workspace import seeding

    bundled = tmp_path / "app" / "workspace" / "skills"
    skill = bundled / "bundled-skill"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: bundled-skill\n---\nx\n", encoding="utf-8")

    app_root = tmp_path / "app"
    monkeypatch.setattr(seeding, "APPLICATION_ROOT", app_root)
    workspace = tmp_path / "users" / "u1" / "workspace"

    seeding.seed_bundled_workspace_resources(workspace, include_skills=False)
    assert not (workspace / "skills").exists()


def test_session_workspace_uses_private_dir_for_regular_user(tmp_path, monkeypatch):
    from backend.modules.workspace import manager

    private = tmp_path / "users" / "u1" / "workspace"
    private.mkdir(parents=True)
    admin_ws = tmp_path / "admin-workspace"
    admin_ws.mkdir(parents=True)

    monkeypatch.setattr(manager, "ensure_user_workspace", lambda uid: private)
    session = SimpleNamespace(workspace_path=str(admin_ws))

    assert manager.resolve_session_workspace(session, user=_regular_user()) == private
    assert manager.resolve_session_workspace(
        session, user=AuthUser(id="admin", username="admin", role="admin")
    ) == admin_ws.resolve()


@pytest.mark.asyncio
async def test_regular_user_cannot_set_session_workspace():
    """普通用户调用会话工作空间接口一律 403（含设置路径与恢复跟随全局）。"""
    from fastapi.testclient import TestClient

    from backend.app import app
    from backend.database import AsyncSessionLocal, init_db
    from backend.models.user import User
    from backend.modules.auth.utils import (
        create_session,
        hash_password,
        revoke_all_sessions,
        revoke_sessions_for_user_id,
    )
    from backend.modules.multiuser import settings as mu_settings

    await init_db()
    original_enabled = (await mu_settings.load_settings(use_cache=False)).enabled
    await mu_settings.save_settings(enabled=True)

    user_id = str(uuid.uuid4())
    username = f"{PREFIX}{user_id[:8]}"
    try:
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
        client = TestClient(app)
        headers = {"Authorization": f"Bearer {token}"}
        endpoint = "/api/chat/sessions/__boundary__/workspace"

        assert client.put(endpoint, json={"path": "/outside-workspace"}, headers=headers).status_code == 403
        assert client.put(endpoint, json={"path": None}, headers=headers).status_code == 403
    finally:
        async with AsyncSessionLocal() as session:
            row = await session.get(User, user_id)
            if row is not None:
                await session.delete(row)
                await session.commit()
        revoke_sessions_for_user_id(user_id)
        revoke_all_sessions(username)
        await mu_settings.save_settings(enabled=original_enabled)


@pytest.mark.asyncio
async def test_regular_user_persona_does_not_inherit_admin_private_fields(monkeypatch):
    """全局人设可以共享，但管理员的称呼、地址与主动问候不能下发给普通用户。"""
    from types import SimpleNamespace

    from backend.modules.config.schema import PersonaConfig
    from backend.modules.multiuser import effective

    admin_persona = PersonaConfig(
        user_name="管理员",
        user_address="管理员地址",
        heartbeat={"enabled": True, "channel": "feishu", "chat_id": "admin-chat"},
    )
    monkeypatch.setattr(
        effective,
        "config_loader",
        SimpleNamespace(config=SimpleNamespace(persona=admin_persona)),
    )

    async def _empty(_user_id):
        return {}

    monkeypatch.setattr(effective, "load_user_config", _empty)

    persona = await effective.resolve_persona_for_user(_regular_user())
    defaults = PersonaConfig()
    assert persona.ai_name == admin_persona.ai_name
    assert persona.user_name == defaults.user_name
    assert persona.user_address == ""
    assert persona.heartbeat.enabled is False


@pytest.mark.asyncio
async def test_regular_user_cannot_resolve_admin_only_model(monkeypatch):
    """普通用户显式指定供应商时，只能命中自己的模型或已共享模型。"""
    from types import SimpleNamespace

    from backend.modules.multiuser import effective
    from backend.modules.multiuser import settings as mu_settings

    async def _empty(_user_id):
        return {}

    async def _disabled_sharing(use_cache=True):
        return SimpleNamespace(mode="shared", shared_providers=False)

    monkeypatch.setattr(effective, "load_user_config", _empty)
    monkeypatch.setattr(mu_settings, "load_settings", _disabled_sharing)

    with pytest.raises(effective.ModelResolutionError):
        await effective.resolve_model_ref_for_user(
            _regular_user(), "admin-provider", "admin-model"
        )
