"""用户自建 MCP 的校验、隔离与注册测试。"""

import asyncio
import sys
from pathlib import Path

import pytest
import pytest_asyncio

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.modules.config.schema import McpServerConfig
from backend.modules.mcp.helpers import _qualify_name
from backend.modules.multiuser.settings import MultiuserSettings
from backend.modules.multiuser.user_mcp import (
    MASK_VALUE,
    MAX_USER_MCP_SERVERS,
    USER_TOOL_PREFIX,
    UserMcpError,
    UserMcpManager,
    mask_server_config,
    owner_server_prefix,
    prepare_server,
    prepare_server_list,
    restore_masked_config,
)
from backend.modules.tools.base import Tool
from backend.modules.tools.registry import ToolRegistry


class DummyTool(Tool):
    def __init__(self, name):
        self._name = name

    @property
    def name(self):
        return self._name

    @property
    def description(self):
        return self._name

    @property
    def parameters(self):
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs):
        return self._name


@pytest.fixture(autouse=True)
def _stub_dns(monkeypatch):
    """避免单测依赖外网 DNS；字面量内网 IP 仍会被 SSRF 拦截。"""
    monkeypatch.setattr(
        "backend.modules.multiuser.ssrf._resolve_host_ips",
        lambda host: {"93.184.216.34"},
    )


def _http_server(**overrides) -> McpServerConfig:
    data = {
        "id": "demo",
        "name": "demo",
        "transport": "streamable_http",
        "url": "https://example.com/mcp",
    }
    data.update(overrides)
    return McpServerConfig(**data)


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://mcp.example.com/mcp",          # 非 HTTPS
        "https://127.0.0.1/mcp",               # 回环
        "https://192.168.1.10/mcp",            # 私网
        "https://169.254.169.254/mcp",         # 链路本地 / 元数据
        "https://test-user:test-placeholder@mcp.example.com/mcp",
    ],
)
def test_http_url_rejected_by_ssrf(url):
    with pytest.raises(UserMcpError):
        prepare_server(_http_server(url=url))


def test_http_url_allows_public_https():
    ready = prepare_server(_http_server())
    assert ready.transport == "streamable_http"
    assert ready.url == "https://example.com/mcp"


def test_stdio_requires_admin_allowlist():
    config = McpServerConfig(id="local", name="local", transport="stdio", command="npx")
    with pytest.raises(UserMcpError):
        prepare_server(config, allowlist=())

    ready = prepare_server(config, allowlist=("npx",))
    assert ready.transport == "stdio"


def test_stdio_rejects_shell_and_metacharacters():
    with pytest.raises(UserMcpError):
        prepare_server(
            McpServerConfig(id="x", name="x", transport="stdio", command="bash"),
            allowlist=("bash",),
        )

    with pytest.raises(UserMcpError):
        prepare_server(
            McpServerConfig(id="x", name="x", transport="stdio", command="npx;rm"),
            allowlist=("npx;rm",),
        )


def test_stdio_env_is_minimal_and_rejects_loader_vars(monkeypatch):
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "super-secret")
    config = McpServerConfig(
        id="local",
        name="local",
        transport="stdio",
        command="npx",
        env={"MY_TOKEN": "ok"},
    )
    ready = prepare_server(config, allowlist=("npx",))
    assert ready.env["MY_TOKEN"] == "ok"
    assert "AWS_SECRET_ACCESS_KEY" not in ready.env, "不得继承宿主敏感环境变量"

    with pytest.raises(UserMcpError):
        prepare_server(
            McpServerConfig(
                id="bad",
                name="bad",
                transport="stdio",
                command="npx",
                env={"LD_PRELOAD": "evil.so"},
            ),
            allowlist=("npx",),
        )


def test_server_limit_and_duplicate_ids():
    servers = [_http_server(id=f"s{i}", name=f"s{i}") for i in range(MAX_USER_MCP_SERVERS + 1)]
    with pytest.raises(UserMcpError):
        prepare_server_list(servers, allowlist=())

    duplicated = [_http_server(id="same", name="a"), _http_server(id="same", name="b")]
    with pytest.raises(UserMcpError):
        prepare_server_list(duplicated, allowlist=())


def test_invalid_id_is_rejected():
    with pytest.raises(UserMcpError):
        prepare_server(_http_server(id="bad id!"))


# ---------------------------------------------------------------------------
# 脱敏
# ---------------------------------------------------------------------------


def test_mask_and_restore_secrets():
    original = _http_server(headers={"Authorization": "Bearer real-token"})
    masked = mask_server_config(original)
    assert masked["headers"]["Authorization"] == MASK_VALUE

    incoming = _http_server(headers={"Authorization": MASK_VALUE})
    restored = restore_masked_config(incoming, original)
    assert restored.headers["Authorization"] == "Bearer real-token"


# ---------------------------------------------------------------------------
# 命名空间隔离
# ---------------------------------------------------------------------------


def test_reconcile_only_touches_user_namespace():
    mgr = UserMcpManager()._get_manager("owner")  # noqa: SLF001 - 单测直接取内部实例
    keep = DummyTool("mcp__admin__search")
    user_tool = DummyTool(f"{USER_TOOL_PREFIX}owner-demo__echo")
    mgr._connected = True  # noqa: SLF001
    mgr._tool_wrappers = {user_tool.name: user_tool}  # noqa: SLF001

    registry = ToolRegistry()
    registry.register(keep)
    registry.register(DummyTool(f"{USER_TOOL_PREFIX}owner-old__gone"))

    mgr.reconcile_registry_sync(registry, prefix=USER_TOOL_PREFIX)

    assert registry.has_tool("mcp__admin__search"), "管理员 MCP 工具不得被用户管理器删除"
    assert registry.has_tool(user_tool.name)
    assert not registry.has_tool(f"{USER_TOOL_PREFIX}owner-old__gone")


class _FakeStack:
    async def aclose(self):
        pass


def test_sync_registers_prefixed_tools(monkeypatch):
    """用户 MCP 工具必须带 ``mcp__usr-`` 前缀，且只进入自己的注册表。"""
    from backend.modules.mcp import client as mcp_client
    from backend.modules.multiuser import user_mcp as user_mcp_module

    settings = MultiuserSettings(enabled=True, allow_user_mcp=True)
    monkeypatch.setattr(
        "backend.modules.multiuser.settings.peek_settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        user_mcp_module,
        "load_user_mcp_servers",
        lambda owner_id: _async_value([_http_server()]),
    )

    async def fake_connect(server_id, cfg, registry, out_wrappers=None):
        tool = DummyTool(_qualify_name(server_id, "echo"))
        registry.register(tool)
        if out_wrappers is not None:
            out_wrappers[tool.name] = tool
        return _FakeStack()

    monkeypatch.setattr(mcp_client, "connect_mcp_server", fake_connect)

    async def scenario():
        manager = UserMcpManager()
        registry_a = ToolRegistry()
        registry_b = ToolRegistry()

        count = await manager.sync_into_registry("owner-a", registry_a)
        await manager.sync_into_registry("owner-b", registry_b)

        prefix = owner_server_prefix("owner-a")
        expected = _qualify_name(f"{prefix}demo", "echo")
        assert count == 1
        assert registry_a.has_tool(expected)
        assert expected.startswith(USER_TOOL_PREFIX)
        assert all(name.startswith(USER_TOOL_PREFIX) for name in registry_a.list_tools())
        assert expected not in registry_b.list_tools()

        # 幂等：再次同步不重复注册
        again = await manager.sync_into_registry("owner-a", registry_a)
        assert again == 1
        assert len([n for n in registry_a.list_tools() if n.startswith(USER_TOOL_PREFIX)]) == 1

        await manager.disconnect("owner-a")
        await manager.disconnect("owner-b")

    asyncio.run(scenario())


async def _async_value(value):
    return value


# ---------------------------------------------------------------------------
# API 层：权限、脱敏、用户间隔离
# ---------------------------------------------------------------------------

API_TEST_PASSWORD = "test-placeholder"
API_PREFIX = "__usermcp_test_"


@pytest_asyncio.fixture
async def _auth_configured():
    """RemoteAuthMiddleware 在管理员未初始化时会 401，这里临时补一份凭据。"""
    from backend.modules.auth.router import get_stored_credentials, save_credentials
    from backend.modules.auth.utils import hash_password

    original_username, original_hash = await get_stored_credentials()
    if not original_hash:
        await save_credentials("__usermcp_admin__", hash_password(API_TEST_PASSWORD))
    try:
        yield
    finally:
        if not original_hash:
            await save_credentials(original_username, original_hash)


async def _create_api_user():
    import uuid

    from backend.database import AsyncSessionLocal
    from backend.models.user import User
    from backend.modules.auth.utils import hash_password

    user_id = str(uuid.uuid4())
    username = f"{API_PREFIX}{user_id[:8]}"
    async with AsyncSessionLocal() as session:
        session.add(
            User(
                id=user_id,
                username=username,
                password_hash=hash_password(API_TEST_PASSWORD),
                role="user",
                status="active",
            )
        )
        await session.commit()
    return user_id, username


async def _api_token(user_id: str, username: str) -> str:
    from backend.modules.auth.utils import create_session

    return create_session(username, user_id=user_id)


async def _cleanup_api_user(user_id: str, username: str) -> None:
    from backend.database import AsyncSessionLocal
    from backend.models.user import User, UserConfig
    from backend.modules.auth.utils import revoke_all_sessions, revoke_sessions_for_user_id

    async with AsyncSessionLocal() as session:
        config = await session.get(UserConfig, user_id)
        if config is not None:
            await session.delete(config)
        user = await session.get(User, user_id)
        if user is not None:
            await session.delete(user)
        await session.commit()
    revoke_sessions_for_user_id(user_id)
    revoke_all_sessions(username)


@pytest.mark.asyncio
async def test_me_mcp_api_masks_and_isolates(_auth_configured):
    """/api/me/mcp 只对普通用户开放，返回脱敏配置，且用户间互不可见。"""
    from fastapi.testclient import TestClient

    from backend.app import app
    from backend.database import init_db
    from backend.modules.multiuser.settings import invalidate_cache

    await init_db()
    invalidate_cache()

    from backend.modules.multiuser import settings as mu_settings

    original_enabled = (await mu_settings.load_settings(use_cache=False)).enabled
    await mu_settings.save_settings(enabled=True)

    a_id, a_name = await _create_api_user()
    b_id, b_name = await _create_api_user()
    try:
        client = TestClient(app)
        token_a = await _api_token(a_id, a_name)
        headers_a = {"Authorization": f"Bearer {token_a}"}

        def _payload(server_id: str = "demo"):
            return {
                "servers": [
                    {
                        "id": server_id,
                        "name": server_id,
                        "transport": "streamable_http",
                        "url": "https://example.com/mcp",
                        "headers": {"Authorization": "Bearer secret-token"},
                    }
                ]
            }

        created = client.put("/api/me/mcp", headers=headers_a, json=_payload())
        assert created.status_code == 200, created.text
        assert "secret-token" not in created.text
        assert MASK_VALUE in created.text

        listing = client.get("/api/me/mcp", headers=headers_a)
        assert listing.status_code == 200
        body = listing.json()
        assert [s["id"] for s in body["servers"]] == ["demo"]
        assert body["servers"][0]["headers"]["Authorization"] == MASK_VALUE
        assert "secret-token" not in listing.text

        token_b = await _api_token(b_id, b_name)
        other = client.get("/api/me/mcp", headers={"Authorization": f"Bearer {token_b}"})
        assert other.status_code == 200
        assert other.json()["servers"] == []

        # SSRF 地址必须被拒绝
        bad = client.put(
            "/api/me/mcp",
            headers=headers_a,
            json={
                "servers": [
                    {
                        "id": "ssrf",
                        "name": "ssrf",
                        "transport": "streamable_http",
                        "url": "https://127.0.0.1/mcp",
                    }
                ]
            },
        )
        assert bad.status_code == 400

        # stdio 默认未开放
        stdio = client.put(
            "/api/me/mcp",
            headers=headers_a,
            json={
                "servers": [
                    {
                        "id": "local",
                        "name": "local",
                        "transport": "stdio",
                        "command": "npx",
                    }
                ]
            },
        )
        assert stdio.status_code == 400
    finally:
        await _cleanup_api_user(a_id, a_name)
        await _cleanup_api_user(b_id, b_name)
        await mu_settings.save_settings(enabled=original_enabled)
