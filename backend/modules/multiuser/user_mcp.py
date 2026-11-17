"""用户自建 MCP：每用户独立实例与工具前缀；HTTP/SSE 走 SSRF 校验，stdio 需白名单。"""

from __future__ import annotations

import asyncio
import os
import re
from typing import Any, Dict, List, Optional

from loguru import logger

from backend.modules.config.schema import McpServerConfig
from backend.modules.mcp.manager import McpClientManager
from backend.modules.multiuser.ssrf import (
    SsrfError,
    assert_outbound_url_allowed,
    validate_outbound_url,
)
from backend.modules.tools.registry import ToolRegistry

# 用户配置在 user_configs.config_json 中的键
USER_MCP_KEY = "mcp"

MAX_USER_MCP_SERVERS = 5
MAX_ARGS = 30
MAX_ARG_LENGTH = 2048
MAX_ENV_ENTRIES = 20
MAX_HEADER_ENTRIES = 20
MAX_SECRET_LENGTH = 4096
MAX_TOOL_FILTERS = 50
MAX_NAME_LENGTH = 60
MAX_DESCRIPTION_LENGTH = 200

MASK_VALUE = "******"

# 用户自建 MCP 的服务器/工具命名空间
SERVER_ID_PREFIX = "usr-"
USER_TOOL_PREFIX = "mcp__usr-"

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
_HEADER_KEY_RE = re.compile(r"^[A-Za-z0-9-]{1,64}$")
_TOOL_NAME_RE = re.compile(r"^[A-Za-z0-9_.*-]{1,64}$")
_COMMAND_META_RE = re.compile(r"[;&|`$(){}<>\n\r\0]")

# 永远拒绝的 shell/脚本解释器：即使用户骗过白名单也不执行
_FORBIDDEN_COMMANDS = frozenset({
    "sh", "bash", "zsh", "fish", "csh", "ksh",
    "cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh", "pwsh.exe",
    "osascript", "wscript", "cscript",
})

# 可以影响子进程加载行为的危险环境变量（与具体运行时无关的提权面）
_FORBIDDEN_ENV_KEYS = frozenset({
    "LD_PRELOAD", "LD_LIBRARY_PATH", "LD_AUDIT",
    "DYLD_INSERT_LIBRARIES", "DYLD_LIBRARY_PATH",
    "NODE_OPTIONS", "PYTHONPATH", "PYTHONSTARTUP", "PYTHONHOME",
    "PERL5OPT", "PERL5LIB", "RUBYOPT", "RUBYLIB",
    "BASH_ENV", "ENV", "GIT_EXEC_PATH", "GIT_CONFIG_GLOBAL",
})

# stdio 子进程只继承这些宿主变量，绝不把整个进程环境（含密钥）传下去
_INHERITED_ENV_KEYS = (
    "PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "TMP", "TEMP",
    "SYSTEMROOT", "SYSTEMDRIVE", "COMSPEC", "APPDATA", "USERPROFILE", "PATHEXT",
)


class UserMcpError(ValueError):
    """用户 MCP 配置未通过校验。"""


# ---------------------------------------------------------------------------
# 配置读取 / 保存
# ---------------------------------------------------------------------------


def _allowed_ports() -> tuple[int, ...]:
    ports = {443}
    raw = os.getenv("COUNTBOT_USER_MCP_ALLOWED_PORTS", "")
    for part in raw.replace("\n", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ports.add(int(part))
        except ValueError:
            logger.warning(f"Ignoring invalid user MCP allowed port: {part!r}")
    return tuple(sorted(ports))


async def load_user_mcp_servers(owner_id: str) -> List[McpServerConfig]:
    """读取并宽松反序列化用户 MCP 配置，非法项跳过。"""
    if not owner_id:
        return []
    from backend.modules.multiuser.user_config import load_user_config

    raw = await load_user_config(owner_id)
    section = raw.get(USER_MCP_KEY)
    items = section.get("servers") if isinstance(section, dict) else None
    if not isinstance(items, list):
        return []

    servers: List[McpServerConfig] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            servers.append(McpServerConfig.model_validate(item))
        except Exception as exc:
            logger.warning(f"Skip invalid user MCP server for {owner_id}: {exc}")
    return servers


async def save_user_mcp_servers(owner_id: str, servers: List[McpServerConfig]) -> None:
    """整体覆盖写入用户 MCP 配置（调用方必须已完成校验）。"""
    from backend.modules.multiuser.user_config import patch_user_config

    await patch_user_config(
        owner_id,
        **{
            USER_MCP_KEY: {
                "servers": [s.model_dump() for s in servers],
            }
        },
    )


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------


def _owner_tag(owner_id: str) -> str:
    """把 owner id 压成工具名前缀，保证不同用户不撞名。"""
    return re.sub(r"[^a-zA-Z0-9]", "", owner_id or "")[:10] or "unknown"


def owner_server_prefix(owner_id: str) -> str:
    return f"{SERVER_ID_PREFIX}{_owner_tag(owner_id)}-"


def prefixed_server_id(owner_id: str, server_id: str) -> str:
    return f"{owner_server_prefix(owner_id)}{server_id}"


def _derive_id(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", name or "").strip("-").lower()
    return slug[:40]


def _check_timeout(config: McpServerConfig) -> None:
    # Pydantic 已限制取值范围，这里再校验直接构造的场景
    if not 5 <= int(config.timeout) <= 300:
        raise UserMcpError("工具超时必须在 5-300 秒之间")
    if not 5 <= int(config.connect_timeout) <= 60:
        raise UserMcpError("连接超时必须在 5-60 秒之间")


def _check_tool_filters(config: McpServerConfig) -> None:
    for label, values in (
        ("include_tools", config.include_tools or []),
        ("exclude_tools", config.exclude_tools or []),
    ):
        if len(values) > MAX_TOOL_FILTERS:
            raise UserMcpError(f"{label} 最多 {MAX_TOOL_FILTERS} 项")
        for value in values:
            if not isinstance(value, str) or not _TOOL_NAME_RE.match(value):
                raise UserMcpError(f"{label} 含有非法工具名: {value!r}")


def _safe_stdio_env(user_env: Dict[str, str]) -> Dict[str, str]:
    """最小环境：宿主白名单 + 用户显式变量（禁止提权类变量）。"""
    env = {key: os.environ[key] for key in _INHERITED_ENV_KEYS if os.environ.get(key)}
    for key, value in (user_env or {}).items():
        if key in _FORBIDDEN_ENV_KEYS:
            raise UserMcpError(f"环境变量 {key} 不允许设置")
        env[key] = value
    return env


def _check_stdio(config: McpServerConfig, allowlist: tuple[str, ...]) -> None:
    command = (config.command or "").strip()
    if not command:
        raise UserMcpError("stdio 类型必须填写 command")
    if _COMMAND_META_RE.search(command):
        raise UserMcpError("command 不允许包含 shell 元字符")
    basename = os.path.basename(command).lower()
    if basename in _FORBIDDEN_COMMANDS:
        raise UserMcpError(f"不允许使用 shell/解释器: {basename}")
    if basename not in {item.lower() for item in allowlist}:
        raise UserMcpError(
            f"命令 '{basename}' 不在管理员白名单内；如需使用 stdio，请联系管理员开启"
        )
    if config.args:
        if len(config.args) > MAX_ARGS:
            raise UserMcpError(f"args 最多 {MAX_ARGS} 项")
        for arg in config.args:
            if not isinstance(arg, str):
                raise UserMcpError("args 必须是字符串数组")
            if len(arg) > MAX_ARG_LENGTH:
                raise UserMcpError(f"单个参数不能超过 {MAX_ARG_LENGTH} 字符")
            if "\x00" in arg or "\n" in arg or "\r" in arg:
                raise UserMcpError("参数不允许包含控制字符")


def _check_env(config: McpServerConfig) -> None:
    if not config.env:
        return
    if len(config.env) > MAX_ENV_ENTRIES:
        raise UserMcpError(f"环境变量最多 {MAX_ENV_ENTRIES} 项")
    for key, value in config.env.items():
        if not isinstance(key, str) or not _ENV_KEY_RE.match(key):
            raise UserMcpError(f"非法环境变量名: {key!r}")
        if key in _FORBIDDEN_ENV_KEYS:
            raise UserMcpError(f"环境变量 {key} 不允许设置")
        if not isinstance(value, str):
            raise UserMcpError(f"环境变量 {key} 的值必须是字符串")
        if len(value) > MAX_SECRET_LENGTH or "\x00" in value:
            raise UserMcpError(f"环境变量 {key} 的值过长或包含非法字符")


def _check_http(config: McpServerConfig) -> None:
    url = (config.url or "").strip()
    if not url:
        raise UserMcpError("HTTP/SSE 类型必须填写 URL")
    try:
        validate_outbound_url(url, allowed_ports=_allowed_ports())
    except SsrfError as exc:
        raise UserMcpError(f"URL 未通过安全校验: {exc}") from exc

    if config.headers:
        if len(config.headers) > MAX_HEADER_ENTRIES:
            raise UserMcpError(f"请求头最多 {MAX_HEADER_ENTRIES} 项")
        for key, value in config.headers.items():
            if not isinstance(key, str) or not _HEADER_KEY_RE.match(key):
                raise UserMcpError(f"非法请求头名称: {key!r}")
            if not isinstance(value, str):
                raise UserMcpError(f"请求头 {key} 的值必须是字符串")
            if len(value) > MAX_SECRET_LENGTH:
                raise UserMcpError(f"请求头 {key} 的值过长")
            if "\x00" in value or "\n" in value or "\r" in value:
                raise UserMcpError(f"请求头 {key} 不允许包含换行或控制字符")


def prepare_server(config: McpServerConfig, *, allowlist: Optional[tuple[str, ...]] = None) -> McpServerConfig:
    """校验并返回可落库的规范化配置；stdio 会重写为最小环境变量集合。"""
    if not config.name or not config.name.strip():
        raise UserMcpError("服务器名称不能为空")
    name = config.name.strip()
    if len(name) > MAX_NAME_LENGTH:
        raise UserMcpError(f"服务器名称不能超过 {MAX_NAME_LENGTH} 字符")

    server_id = (config.id or "").strip() or _derive_id(name)
    if not server_id or not _ID_RE.match(server_id):
        raise UserMcpError("服务器 ID 只能包含字母、数字、下划线和连字符（1-40 位）")

    if config.description and len(config.description) > MAX_DESCRIPTION_LENGTH:
        raise UserMcpError(f"描述不能超过 {MAX_DESCRIPTION_LENGTH} 字符")

    _check_timeout(config)
    _check_tool_filters(config)
    _check_env(config)

    transport = config.transport
    if transport is None:
        if config.command:
            transport = "stdio"
        elif config.url:
            transport = "sse" if config.url.rstrip("/").endswith("/sse") else "streamable_http"
        else:
            raise UserMcpError("必须填写 command（stdio）或 URL（HTTP/SSE）")

    if transport == "stdio":
        if allowlist is None:
            allowlist = ()
        _check_stdio(config, allowlist)
        env = _safe_stdio_env(config.env)
    elif transport in ("streamable_http", "sse"):
        _check_http(config)
        env = {}
    else:
        raise UserMcpError(f"不支持的传输类型: {transport}")

    return config.model_copy(
        update={
            "id": server_id,
            "name": name,
            "transport": transport,
            "env": env,
        }
    )


def prepare_server_list(
    servers: List[McpServerConfig],
    *,
    allowlist: tuple[str, ...],
) -> List[McpServerConfig]:
    """校验整份用户 MCP 列表：数量上限、ID 唯一、逐项安全校验。"""
    if len(servers) > MAX_USER_MCP_SERVERS:
        raise UserMcpError(f"最多配置 {MAX_USER_MCP_SERVERS} 个 MCP 服务器")

    prepared: List[McpServerConfig] = []
    seen: set[str] = set()
    for server in servers:
        ready = prepare_server(server, allowlist=allowlist)
        if ready.id in seen:
            raise UserMcpError(f"服务器 ID 重复: {ready.id}")
        seen.add(ready.id)
        prepared.append(ready)
    return prepared


# ---------------------------------------------------------------------------
# 脱敏
# ---------------------------------------------------------------------------


def mask_server_config(config: McpServerConfig) -> Dict[str, Any]:
    """返回配置副本：env / headers 的值只显示掩码。"""
    data = config.model_dump()
    data["env"] = {key: (MASK_VALUE if value else "") for key, value in config.env.items()}
    data["headers"] = {
        key: (MASK_VALUE if value else "") for key, value in config.headers.items()
    }
    return data


def restore_masked_config(
    incoming: McpServerConfig,
    existing: Optional[McpServerConfig],
) -> McpServerConfig:
    """前端回传掩码时保留数据库中的真实凭证。"""
    if existing is None:
        return incoming

    def _restore(new_values: Dict[str, str], old_values: Dict[str, str]) -> Dict[str, str]:
        merged: Dict[str, str] = {}
        for key, value in new_values.items():
            if value == MASK_VALUE and key in old_values:
                merged[key] = old_values[key]
            else:
                merged[key] = value
        return merged

    return incoming.model_copy(
        update={
            "env": _restore(incoming.env or {}, existing.env or {}),
            "headers": _restore(incoming.headers or {}, existing.headers or {}),
        }
    )


# ---------------------------------------------------------------------------
# 每用户连接管理
# ---------------------------------------------------------------------------


class UserMcpManager:
    """按用户维护独立的 MCP 连接；配置变更时整体回收。"""

    def __init__(self) -> None:
        self._managers: Dict[str, McpClientManager] = {}

    # -- 生命周期 ---------------------------------------------------------

    def _get_manager(self, owner_id: str) -> McpClientManager:
        manager = self._managers.get(owner_id)
        if manager is None:
            manager = McpClientManager(broadcast=False)
            self._managers[owner_id] = manager
        return manager

    async def sync_into_registry(self, owner_id: str, registry: ToolRegistry) -> int:
        """把该用户启用的 MCP 工具注册进其私有注册表，返回工具数。"""
        if not owner_id:
            return 0

        from backend.modules.multiuser.settings import peek_settings

        settings = peek_settings()
        if not settings.allow_user_mcp:
            await self.disconnect(owner_id)
            return 0

        raw_servers = [s for s in await load_user_mcp_servers(owner_id) if s.enabled]
        # 落库后仍重新校验：防止库被篡改或旧版本遗留的不安全配置被直接执行
        servers: List[McpServerConfig] = []
        for server in raw_servers:
            try:
                servers.append(
                    prepare_server(server, allowlist=settings.user_mcp_stdio_allowlist)
                )
            except UserMcpError as exc:
                logger.warning(f"Skip unsafe user MCP server for {owner_id}: {exc}")
        if not servers:
            await self.disconnect(owner_id)
            return 0

        # 建连前重新校验远程地址，防止域名改指向内网
        servers = [s for s in servers if self._url_safe_now(s, owner_id)]
        if not servers:
            await self.disconnect(owner_id)
            return 0

        manager = self._get_manager(owner_id)
        manager.set_registry(registry)

        prefixed = [
            server.model_copy(
                update={
                    "id": prefixed_server_id(owner_id, server.id or server.name),
                    "name": prefixed_server_id(owner_id, server.id or server.name),
                }
            )
            for server in servers
        ]

        if not manager.connected:
            await manager.connect(prefixed)
        else:
            manager.sync_to_registry_sync(registry)

        manager.reconcile_registry_sync(registry, prefix=USER_TOOL_PREFIX)
        # 供每轮对话前对齐工具集（WS 长连接感知配置变更）
        setattr(registry, "user_mcp_manager", manager)
        setattr(registry, "user_mcp_owner", owner_id)

        status = manager.get_status()
        logger.info(
            f"User MCP ready for {owner_id}: "
            f"{len(status.get('servers', []))} server(s), {status.get('tool_count', 0)} tool(s)"
        )
        return int(status.get("tool_count", 0))

    @staticmethod
    def _url_safe_now(server: McpServerConfig, owner_id: str) -> bool:
        """建连前重新校验远程地址；stdio（本地命令）不在本函数职责内。"""
        if not server.url:
            return True
        try:
            assert_outbound_url_allowed(server.url, allowed_ports=_allowed_ports())
            return True
        except SsrfError as exc:
            logger.warning(
                f"Skip user MCP server '{server.id or server.name}' for {owner_id}: {exc}"
            )
            return False

    async def disconnect(self, owner_id: str) -> None:
        manager = self._managers.pop(owner_id, None)
        if manager is None:
            return
        try:
            await manager.disconnect()
        except Exception as exc:
            logger.warning(f"Failed to disconnect user MCP for {owner_id}: {exc}")

    def schedule_disconnect(self, owner_id: str) -> None:
        """同步上下文（如运行时失效）里安全地异步回收连接。"""
        manager = self._managers.pop(owner_id, None)
        if manager is None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(manager.disconnect())

    def get_status(self, owner_id: str) -> Dict[str, Any]:
        manager = self._managers.get(owner_id)
        if manager is None:
            return {"connected": False, "server_status": {}, "tool_count": 0, "tools": []}
        return manager.get_status()

    async def test_server(self, owner_id: str, config: McpServerConfig) -> Dict[str, Any]:
        """测试连接；不落库、不注册工具。"""
        from backend.modules.multiuser.settings import peek_settings

        settings = peek_settings()
        prepared = prepare_server(config, allowlist=settings.user_mcp_stdio_allowlist)

        from backend.modules.mcp.connection import test_mcp_server

        return await test_mcp_server(prepared)


# 全局单例
user_mcp_manager = UserMcpManager()
