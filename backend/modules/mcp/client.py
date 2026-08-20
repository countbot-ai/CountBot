import asyncio
import os
import re
import shutil
from contextlib import AsyncExitStack
from typing import Any, Dict, List, Optional

from loguru import logger

from backend.modules.config.schema import McpServerConfig
from backend.modules.tools.base import Tool
from backend.modules.tools.registry import ToolRegistry

_TRANSIENT_EXC_NAMES: frozenset[str] = frozenset((
    "ClosedResourceError",
    "BrokenResourceError",
    "EndOfStream",
    "BrokenPipeError",
    "ConnectionResetError",
    "ConnectionRefusedError",
    "ConnectionAbortedError",
    "ConnectionError",
))

_WINDOWS_SHELL_LAUNCHERS: frozenset[str] = frozenset((
    "npx", "npm", "pnpm", "yarn", "bunx",
))

_SANITIZE_RE = re.compile(r"_+")


def _sanitize_name(name: str) -> str:
    return _SANITIZE_RE.sub("_", re.sub(r"[^a-zA-Z0-9_-]", "_", name))


def _is_transient(exc: BaseException) -> bool:
    return type(exc).__name__ in _TRANSIENT_EXC_NAMES


def _normalize_windows_stdio_command(
    command: str,
    args: List[str],
    env: Dict[str, str],
) -> tuple[str, List[str], Dict[str, str]]:
    if os.name != "nt":
        return command, args, env
    base = command.lower().strip()
    if base.endswith(".exe") or base.endswith(".com"):
        return command, args, env
    if base in ("cmd", "cmd.exe", "powershell", "pwsh"):
        return command, args, env
    resolved = shutil.which(command)
    if resolved:
        resolved_lower = resolved.lower()
        if resolved_lower.endswith(".exe") or resolved_lower.endswith(".com"):
            return command, args, env
        if resolved_lower.endswith(".cmd") or resolved_lower.endswith(".bat"):
            pass
        elif base not in _WINDOWS_SHELL_LAUNCHERS:
            return command, args, env
    elif base not in _WINDOWS_SHELL_LAUNCHERS:
        return command, args, env
    comspec = env.get("COMSPEC") or os.environ.get("COMSPEC", "cmd.exe")
    new_args = ["/d", "/c", command] + list(args)
    return comspec, new_args, env


def _infer_transport(config: McpServerConfig) -> str:
    if config.transport:
        return config.transport
    if config.command:
        return "stdio"
    if config.url:
        return "sse" if config.url.rstrip("/").endswith("/sse") else "streamable_http"
    return ""


def _normalize_schema_for_openai(schema: dict) -> dict:
    if not isinstance(schema, dict):
        return {"type": "object", "properties": {}}
    if schema.get("type") in (["string", "null"], ["null", "string"]):
        schema = {**schema, "type": "string", "nullable": True}
    if "anyOf" in schema:
        non_null = [s for s in schema["anyOf"] if s.get("type") != "null"]
        if len(non_null) == 1:
            merged = {**non_null[0], "nullable": True}
            for k in ("title", "description", "default"):
                if k in schema and k not in merged:
                    merged[k] = schema[k]
            schema = merged
        else:
            schema = {**schema}
            del schema["anyOf"]
    for key in ("properties", "items"):
        child = schema.get(key)
        if isinstance(child, dict):
            schema = {**schema, key: _normalize_schema_for_openai(child)}
    if "required" in schema and not isinstance(schema["required"], list):
        schema = {**schema, "required": list(schema["required"])}
    return schema


async def _execute_with_retry(coro_factory, timeout: int, label: str) -> str:
    for attempt in range(2):
        try:
            result = await asyncio.wait_for(coro_factory(), timeout=timeout)
            return result
        except asyncio.TimeoutError:
            return f"({label} timed out after {timeout}s)"
        except asyncio.CancelledError:
            task = asyncio.current_task()
            if task is not None and task.cancelling() > 0:
                raise
            return f"({label} was cancelled)"
        except Exception as exc:
            exc_name = type(exc).__name__
            if exc_name == "McpError":
                err = getattr(exc, "error", None)
                code = getattr(err, "code", "?") if err else "?"
                msg = getattr(err, "message", str(exc)) if err else str(exc)
                return f"({label} failed: MCP error {code}: {msg})"
            if _is_transient(exc):
                if attempt == 0:
                    await asyncio.sleep(1)
                    continue
                return f"({label} failed after retry: {exc_name})"
            return f"({label} failed: {exc_name}: {exc})"
    return f"({label} unexpected retry exhaustion)"


class MCPToolWrapper(Tool):
    def __init__(self, session, server_name: str, tool_def, tool_timeout: int = 30):
        self._session = session
        self._original_name = tool_def.name
        self._name = _sanitize_name(f"mcp_{server_name}_{tool_def.name}")
        self._description = tool_def.description or tool_def.name
        raw_schema = tool_def.inputSchema or {"type": "object", "properties": {}}
        self._parameters = _normalize_schema_for_openai(raw_schema)
        self._tool_timeout = tool_timeout

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> Dict[str, Any]:
        return self._parameters

    async def execute(self, **kwargs: Any) -> str:
        result = await _execute_with_retry(
            lambda: self._session.call_tool(self._original_name, arguments=kwargs),
            self._tool_timeout,
            "MCP tool call",
        )
        if isinstance(result, str):
            return result
        parts = []
        for content in (result.content or []):
            if hasattr(content, "text"):
                parts.append(content.text)
            else:
                parts.append(str(content))
        return "\n".join(parts) if parts else "(MCP tool returned empty result)"


class MCPResourceWrapper(Tool):
    def __init__(self, session, server_name: str, resource_def, resource_timeout: int = 30):
        self._session = session
        self._name = _sanitize_name(f"mcp_{server_name}_resource_{resource_def.name}")
        self._uri = str(resource_def.uri)
        desc = resource_def.description or resource_def.name
        self._description = f"[MCP Resource] {desc}\nURI: {self._uri}"
        self._parameters: Dict[str, Any] = {"type": "object", "properties": {}}
        self._resource_timeout = resource_timeout

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> Dict[str, Any]:
        return self._parameters

    async def execute(self, **kwargs: Any) -> str:
        result = await _execute_with_retry(
            lambda: self._session.read_resource(self._uri),
            self._resource_timeout,
            "MCP resource read",
        )
        if isinstance(result, str):
            return result
        parts = []
        for content in (result.contents or []):
            if hasattr(content, "text"):
                parts.append(content.text)
            else:
                parts.append(str(content))
        return "\n".join(parts) if parts else "(MCP resource returned empty)"


class MCPPromptWrapper(Tool):
    def __init__(self, session, server_name: str, prompt_def, prompt_timeout: int = 30):
        self._session = session
        self._prompt_name = prompt_def.name
        self._name = _sanitize_name(f"mcp_{server_name}_prompt_{prompt_def.name}")
        desc = prompt_def.description or prompt_def.name
        self._description = f"[MCP Prompt] {desc}"
        self._prompt_timeout = prompt_timeout
        properties: Dict[str, Any] = {}
        required: List[str] = []
        if prompt_def.arguments:
            for arg in prompt_def.arguments:
                prop: Dict[str, Any] = {"type": "string", "description": arg.description or arg.name}
                if arg.required:
                    required.append(arg.name)
                properties[arg.name] = prop
        self._parameters: Dict[str, Any] = {
            "type": "object",
            "properties": properties,
            "required": required,
        }

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> Dict[str, Any]:
        return self._parameters

    async def execute(self, **kwargs: Any) -> str:
        result = await _execute_with_retry(
            lambda: self._session.get_prompt(self._prompt_name, arguments=kwargs),
            self._prompt_timeout,
            "MCP prompt",
        )
        if isinstance(result, str):
            return result
        parts = []
        for msg in (result.messages or []):
            if hasattr(msg, "content") and hasattr(msg.content, "text"):
                parts.append(msg.content.text)
            else:
                parts.append(str(msg))
        return "\n".join(parts) if parts else "(MCP prompt returned empty)"


async def connect_mcp_server(
    name: str,
    config: McpServerConfig,
    registry: ToolRegistry,
    out_wrappers: Optional[Dict[str, Tool]] = None,
) -> Optional[AsyncExitStack]:
    try:
        from mcp.client.stdio import stdio_client
        from mcp.client.sse import sse_client
        from mcp.client.streamable_http import streamable_http_client
        from mcp import ClientSession
    except ImportError:
        logger.error("mcp package not installed, run: pip install mcp")
        return None

    transport_type = _infer_transport(config)
    if not transport_type:
        logger.warning(f"MCP server '{name}': no command or url configured, skipping")
        return None

    stack = AsyncExitStack()
    try:
        await stack.__aenter__()

        connect_timeout = config.connect_timeout or 10

        if transport_type == "stdio":
            if not config.command:
                logger.warning(f"MCP server '{name}': stdio transport requires 'command', skipping")
                await stack.__aexit__(None, None, None)
                return None
            command, args, env = _normalize_windows_stdio_command(
                config.command, config.args, config.env,
            )
            from mcp.client.stdio import StdioServerParameters
            server_params = StdioServerParameters(
                command=command,
                args=args,
                env=env or None,
            )
            read, write = await stack.enter_async_context(stdio_client(server_params))
        elif transport_type == "sse":
            if not config.url:
                logger.warning(f"MCP server '{name}': sse transport requires 'url', skipping")
                await stack.__aexit__(None, None, None)
                return None
            read, write = await stack.enter_async_context(
                sse_client(url=config.url, headers=config.headers or None)
            )
        elif transport_type == "streamable_http":
            if not config.url:
                logger.warning(f"MCP server '{name}': streamable_http transport requires 'url', skipping")
                await stack.__aexit__(None, None, None)
                return None
            import httpx
            http_client = None
            if config.headers:
                http_client = httpx.AsyncClient(headers=config.headers)
            result = await stack.enter_async_context(
                streamable_http_client(url=config.url, http_client=http_client)
            )
            read, write = result[0], result[1]
        else:
            logger.warning(f"MCP server '{name}': unknown transport '{transport_type}', skipping")
            await stack.__aexit__(None, None, None)
            return None

        session = await asyncio.wait_for(
            stack.enter_async_context(ClientSession(read, write)),
            timeout=connect_timeout,
        )
        await asyncio.wait_for(session.initialize(), timeout=connect_timeout)

    except asyncio.TimeoutError:
        logger.error(f"MCP server '{name}': connection timed out after {connect_timeout}s")
        await stack.__aexit__(None, None, None)
        return None
    except Exception as exc:
        logger.error(f"MCP server '{name}': connection failed: {type(exc).__name__}: {exc}")
        try:
            await stack.aclose()
        except Exception:
            pass
        return None

    try:
        enabled_tools = set(config.include_tools or ["*"])
        allow_all = "*" in enabled_tools
        exclude_set = set(config.exclude_tools or [])
        tool_timeout = config.timeout or 30

        tools_result = await session.list_tools()
        registered = 0
        matched_tools: set[str] = set()
        available_raw: list[str] = []
        available_wrapped: list[str] = []

        for tool_def in tools_result.tools:
            wrapped_name = _sanitize_name(f"mcp_{name}_{tool_def.name}")
            available_raw.append(tool_def.name)
            available_wrapped.append(wrapped_name)
            if not allow_all and tool_def.name not in enabled_tools and wrapped_name not in enabled_tools:
                continue
            if tool_def.name in exclude_set or wrapped_name in exclude_set:
                continue
            if tool_def.name in enabled_tools:
                matched_tools.add(tool_def.name)
            if wrapped_name in enabled_tools:
                matched_tools.add(wrapped_name)
            try:
                wrapper = MCPToolWrapper(session, name, tool_def, tool_timeout=tool_timeout)
                registry.register(wrapper)
                if out_wrappers is not None:
                    out_wrappers[wrapper.name] = wrapper
                registered += 1
            except ValueError:
                logger.warning(f"MCP tool '{wrapped_name}' already registered, skipping")

        if not allow_all and enabled_tools:
            unmatched = sorted(enabled_tools - matched_tools)
            if unmatched:
                logger.warning(
                    f"MCP server '{name}': include_tools entries not found: {unmatched}. "
                    f"Available: {available_raw[:20]}"
                )

        if config.enable_resources:
            try:
                resources_result = await session.list_resources()
                for resource in resources_result.resources:
                    try:
                        wrapper = MCPResourceWrapper(session, name, resource, resource_timeout=tool_timeout)
                        registry.register(wrapper)
                        if out_wrappers is not None:
                            out_wrappers[wrapper.name] = wrapper
                        registered += 1
                    except ValueError:
                        logger.debug(f"MCP resource already registered, skipping")
            except Exception as exc:
                logger.debug(f"MCP server '{name}': resources not supported: {exc}")

        if config.enable_prompts:
            try:
                prompts_result = await session.list_prompts()
                for prompt in prompts_result.prompts:
                    try:
                        wrapper = MCPPromptWrapper(session, name, prompt, prompt_timeout=tool_timeout)
                        registry.register(wrapper)
                        if out_wrappers is not None:
                            out_wrappers[wrapper.name] = wrapper
                        registered += 1
                    except ValueError:
                        logger.debug(f"MCP prompt already registered, skipping")
            except Exception as exc:
                logger.debug(f"MCP server '{name}': prompts not supported: {exc}")

        logger.info(f"MCP server '{name}': connected ({transport_type}), registered {registered} capabilities")
        return stack
    except Exception as exc:
        logger.error(f"MCP server '{name}': tool discovery failed: {exc}")
        try:
            await stack.aclose()
        except Exception:
            pass
        return None


async def test_mcp_server(config: McpServerConfig) -> Dict[str, Any]:
    try:
        from mcp.client.stdio import stdio_client
        from mcp.client.sse import sse_client
        from mcp.client.streamable_http import streamable_http_client
        from mcp import ClientSession
    except ImportError:
        return {"success": False, "message": "mcp package not installed, run: pip install mcp"}

    transport_type = _infer_transport(config)
    if not transport_type:
        return {"success": False, "message": "no command or url configured"}

    resolved_command = None
    normalized_url = None
    connect_timeout = config.connect_timeout or 10
    stack = AsyncExitStack()

    try:
        if transport_type == "stdio":
            if not config.command:
                return {"success": False, "message": "stdio transport requires 'command'"}
            command, args, env = _normalize_windows_stdio_command(
                config.command, config.args, config.env,
            )
            resolved_command = command
            from mcp.client.stdio import StdioServerParameters
            server_params = StdioServerParameters(
                command=command,
                args=args,
                env=env or None,
            )
            read, write = await stack.enter_async_context(stdio_client(server_params))
        elif transport_type == "sse":
            if not config.url:
                return {"success": False, "message": "sse transport requires 'url'"}
            normalized_url = config.url
            read, write = await stack.enter_async_context(
                sse_client(url=config.url, headers=config.headers or None)
            )
        elif transport_type == "streamable_http":
            if not config.url:
                return {"success": False, "message": "streamable_http transport requires 'url'"}
            normalized_url = config.url
            import httpx
            http_client = None
            if config.headers:
                http_client = httpx.AsyncClient(headers=config.headers)
            result = await stack.enter_async_context(
                streamable_http_client(url=config.url, http_client=http_client)
            )
            read, write = result[0], result[1]
        else:
            return {"success": False, "message": f"unknown transport '{transport_type}'"}

        async with ClientSession(read, write) as session:
            await session.initialize()
            tools_result = await session.list_tools()
            tool_names = [t.name for t in tools_result.tools]
            return {
                "success": True,
                "message": f"Connected successfully ({transport_type}), found {len(tool_names)} tools: {', '.join(tool_names[:10])}",
                "resolved_command": resolved_command,
                "normalized_url": normalized_url,
            }
    except Exception as exc:
        import traceback
        tb = traceback.format_exc()
        logger.warning(f"MCP test connection failed: {type(exc).__name__}: {exc}\n{tb}")
        return {"success": False, "message": f"Connection failed: {type(exc).__name__}: {exc}"}
    finally:
        await stack.aclose()


class McpClientManager:
    _instance: Optional["McpClientManager"] = None
    _lock: asyncio.Lock = None  # 类级别锁，用于单例创建

    def __init__(self):
        # 每个 server 的“连接持有者任务”与其停止信号。
        # 关键不变量：某条 stdio/sse/http 连接的 AsyncExitStack 必须在
        # “进入它的那个任务”里退出（anyio cancel scope 要求），否则会抛
        # RuntimeError: Attempted to exit cancel scope in a different task。
        # 因此连接的 open/hold/close 全部锁死在 _run_server_connection 这一个任务内，
        # 外部只通过 _stop_events 发信号、绝不跨任务 aclose()。
        self._conn_tasks: Dict[str, asyncio.Task] = {}
        self._stop_events: Dict[str, asyncio.Event] = {}
        # 用户在运行时“显式停止”的 server：即便全局 MCP 开关仍开着，
        # 也不应被 ensure_connected / reconnect_all 的惰性自动连接重新拉起，
        # 否则“停止”会被下一次状态轮询立刻撤销（按钮停不下来）。
        self._manually_stopped: set = set()
        self._connected = False
        self._connecting = False
        self._registry: Optional[ToolRegistry] = None
        self._mcp_tool_names: List[str] = []
        self._server_configs: Dict[str, McpServerConfig] = {}
        self._reconnect_task: Optional[asyncio.Task] = None
        self._health_check_interval: int = 60
        self._max_reconnect_attempts: int = 3
        self._reconnect_backoff_base: float = 5.0
        # 关闭单条连接时 aclose 的超时上限（秒），防止关闭卡死持有者任务
        self._close_timeout: float = 10.0
        # Store tool wrappers for syncing to new registries
        self._tool_wrappers: Dict[str, Tool] = {}
        # 实例级别锁，用于保护并发操作
        self._operation_lock = asyncio.Lock()

    @classmethod
    async def get_instance_async(cls) -> "McpClientManager":
        """异步获取单例实例（线程安全）"""
        if cls._lock is None:
            cls._lock = asyncio.Lock()

        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @classmethod
    def get_instance(cls) -> "McpClientManager":
        """同步获取单例实例（保持向后兼容）

        注意：在异步环境中应优先使用 get_instance_async()
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def set_registry(self, registry: ToolRegistry) -> None:
        self._registry = registry

    async def ensure_connected(self) -> bool:
        """确保MCP已连接，未连接则尝试连接（延迟初始化）。

        采用延迟连接策略：首次访问时自动建立连接。
        Returns True if connected (or already was).
        """
        if self._connected:
            return True
        if self._connecting:
            return False
        if not self._server_configs:
            return False
        if self._registry is None:
            return False
        from backend.modules.config.loader import config_loader
        if not config_loader.config.mcp.enabled:
            return False
        servers = [
            cfg for cfg in self._server_configs.values()
            if cfg.enabled and (cfg.id or cfg.name or "unknown") not in self._manually_stopped
        ]
        if not servers:
            return False
        await self.connect(servers)
        return self._connected

    @property
    def connected(self) -> bool:
        return self._connected

    def _unregister_mcp_tools(self) -> None:
        if self._registry is None:
            return
        for name in self._mcp_tool_names:
            try:
                self._registry.unregister(name)
            except (KeyError, ValueError):
                pass
        self._mcp_tool_names.clear()
        self._connected = False

    def sync_to_registry_sync(self, registry: ToolRegistry) -> int:
        """Sync MCP tools to a new registry (e.g., per-WebSocket registry).

        同步版本，用于非异步上下文（如WebSocket连接初始化）

        Returns the number of tools synced.
        """
        if not self._connected or not self._tool_wrappers:
            return 0
        synced = 0
        for name, tool in self._tool_wrappers.items():
            if not registry.has_tool(name):
                try:
                    registry.register(tool)
                    synced += 1
                except ValueError:
                    logger.debug(f"Tool {name} already registered in target registry")
        if synced:
            logger.debug(f"Synced {synced} MCP tools to new registry")
        return synced

    def reconcile_registry_sync(self, registry: ToolRegistry) -> int:
        """把某个会话级 registry 的 MCP 工具与“当前全局 MCP 工具集”全量对齐。

        与 sync_to_registry_sync（只增不减）不同，这里做增/删/换：
          - 新增：manager 有、registry 没有的工具
          - 移除：registry 里以 mcp_ 开头、但 manager 当前已无的工具（配置删了/禁用了）
          - 替换：wrapper 对象已更换（重连后指向新 session）的旧工具

        用途：在每轮对话开始前调用，使“中途改了 MCP 配置”的老对话也能在下一条
        消息加载到最新工具。同步、无 await、在事件循环上原子执行；幂等。

        Returns 变更的工具数（新增 + 移除/替换）。
        """
        current = dict(self._tool_wrappers) if self._connected else {}
        changed = 0

        # 移除已不存在、或对象已变（重连）的旧 MCP 工具
        for name in list(registry.list_tools()):
            if not name.startswith("mcp_"):
                continue
            cur = current.get(name)
            if cur is None or registry.get_tool(name) is not cur:
                try:
                    registry.unregister(name)
                    changed += 1
                except (KeyError, ValueError):
                    pass

        # 新增/补齐当前工具
        for name, tool in current.items():
            if not registry.has_tool(name):
                try:
                    registry.register(tool)
                    changed += 1
                except ValueError:
                    pass

        if changed:
            logger.debug(f"Reconciled MCP tools into session registry: {changed} change(s)")
        return changed

    async def sync_to_registry(self, registry: ToolRegistry) -> int:
        """Sync MCP tools to a new registry (e.g., per-WebSocket registry).

        异步版本，线程安全

        Returns the number of tools synced.
        """
        async with self._operation_lock:
            return self.sync_to_registry_sync(registry)

    async def connect(self, servers: List[McpServerConfig]) -> None:
        """连接MCP服务器（线程安全）"""
        async with self._operation_lock:
            if self._connected or self._connecting:
                logger.debug("MCP already connected or connecting, skipping")
                return
            if not servers:
                logger.debug("No servers to connect")
                return
            self._connecting = True

        try:
            enabled_servers = [s for s in servers if s.enabled]
            if not enabled_servers:
                return

            if self._registry is None:
                logger.warning("McpClientManager: registry not set, cannot connect")
                return

            for cfg in enabled_servers:
                server_id = cfg.id or cfg.name or "unknown"
                self._server_configs[server_id] = cfg

            # 每个 server 各起一个“持有者任务”，并发等待各自“首次连接就绪”。
            # 连接的 open/hold/close 全部发生在持有者任务内部（见 _run_server_connection），
            # 这里只负责等待就绪结果，绝不持有或跨任务关闭连接。
            await asyncio.gather(
                *[
                    self._start_connection(cfg.id or cfg.name or "unknown", cfg)
                    for cfg in enabled_servers
                ],
                return_exceptions=True,
            )

            if self._conn_tasks:
                self._connected = True
                logger.info(f"MCP connected: {len(self._conn_tasks)} servers, {len(self._mcp_tool_names)} tools")
                self._start_health_check()

                # 通知所有活跃的WebSocket会话MCP已连接
                try:
                    from backend.modules.websocket.broadcast import broadcast_mcp_status_change
                    await broadcast_mcp_status_change(connected=True)
                except Exception as e:
                    logger.debug(f"Failed to broadcast MCP status change: {e}")
            else:
                logger.warning("No MCP servers connected successfully (will retry next message)")
        finally:
            self._connecting = False

    # ---- 连接生命周期：open/hold/close 全部锁死在“持有者任务”内 -----------

    async def _run_server_connection(
        self, server_id: str, cfg: McpServerConfig, ready: asyncio.Future
    ) -> None:
        """单个 server 的连接持有者任务：在“本任务”内 open → hold → close。

        - open ：connect_mcp_server 在本任务里 enter 传输的 AsyncExitStack
        - hold ：await stop_event.wait()，挂起持有连接
        - close：finally 里在“本任务”内关闭 stack —— 满足 anyio“同任务退出 cancel scope”的要求
        ready 用于把“首次连接结果”回报给发起方（True/False）。
        """
        stop = asyncio.Event()
        self._stop_events[server_id] = stop
        stack: Optional[AsyncExitStack] = None
        registered: List[str] = []
        try:
            stack = await connect_mcp_server(
                server_id, cfg, self._registry, out_wrappers=self._tool_wrappers
            )
            if stack is None:
                if not ready.done():
                    ready.set_result(False)
                return
            registered = [
                n for n in self._registry.list_tools()
                if n.startswith(f"mcp_{server_id}_")
            ]
            for n in registered:
                if n not in self._mcp_tool_names:
                    self._mcp_tool_names.append(n)
            logger.info(f"MCP server '{server_id}': connected, holding {len(registered)} tools")
            if not ready.done():
                ready.set_result(True)
            await stop.wait()  # 持有连接，直到被要求停止（stop.set）或被取消
        except asyncio.CancelledError:
            logger.info(f"MCP server '{server_id}': connection task cancelled")
            raise
        except Exception as exc:
            logger.error(f"MCP server '{server_id}': connection error: {type(exc).__name__}: {exc}")
            if not ready.done():
                ready.set_result(False)
        finally:
            # 关键：正常停止或被取消，都在“本任务”内关闭 stack。
            # 被取消时 stack.aclose() 让 anyio 在同任务解开 cancel scope 并终止子进程（B 兜底强杀）。
            if stack is not None:
                await self._safe_aclose(stack, server_id)
            self._unregister_names(registered)
            self._stop_events.pop(server_id, None)
            # 仅当登记的仍是“自己”这个任务时才移除，避免误删重连后新建的任务
            if self._conn_tasks.get(server_id) is asyncio.current_task():
                self._conn_tasks.pop(server_id, None)

    async def _safe_aclose(self, stack: AsyncExitStack, server_id: str) -> None:
        """在本任务内关闭 stack；带超时与兜底，绝不卡死持有者任务或向外抛出。"""
        try:
            await asyncio.wait_for(stack.aclose(), timeout=self._close_timeout)
        except asyncio.TimeoutError:
            logger.warning(f"MCP server '{server_id}': aclose timed out after {self._close_timeout}s")
        except (RuntimeError, BaseExceptionGroup) as exc:
            # 同任务关闭理论上不再出现 cancel-scope 错误；保留为兜底日志
            logger.warning(f"MCP server '{server_id}': aclose raised {type(exc).__name__}: {exc}")
        except Exception as exc:
            logger.warning(f"MCP server '{server_id}': aclose unexpected error: {exc}")

    def _unregister_names(self, names: List[str]) -> None:
        for n in names:
            try:
                self._registry.unregister(n)
            except (KeyError, ValueError):
                pass
            if n in self._mcp_tool_names:
                self._mcp_tool_names.remove(n)
            self._tool_wrappers.pop(n, None)

    async def _start_connection(self, server_id: str, cfg: McpServerConfig) -> bool:
        """（重新）建立某 server 的连接：先停旧持有者任务，再起新任务并等待就绪。"""
        if self._registry is None:
            logger.warning(f"MCP server '{server_id}': registry not set, cannot connect")
            return False
        # 显式连接即“希望它运行”，撤销之前的手动停止标记
        self._manually_stopped.discard(server_id)
        if server_id in self._conn_tasks:
            await self._stop_connection(server_id)
        ready: asyncio.Future = asyncio.get_event_loop().create_future()
        task = asyncio.create_task(self._run_server_connection(server_id, cfg, ready))
        self._conn_tasks[server_id] = task
        try:
            return bool(await ready)
        except Exception:
            return False

    async def _stop_connection(self, server_id: str, timeout: float = 5.0) -> None:
        """停止某 server 的持有者任务：先发 stop 信号优雅退出；超时则强制取消。

        取消会让持有者任务在“本任务”内解开 AsyncExitStack，
        anyio 借此终止子进程 —— 即所选方案的“B 兜底：强杀”。
        """
        stop = self._stop_events.get(server_id)
        task = self._conn_tasks.get(server_id)
        if stop is not None:
            stop.set()
        if task is not None and not task.done():
            done, _ = await asyncio.wait({task}, timeout=timeout)
            if task not in done:
                logger.warning(f"MCP server '{server_id}': graceful stop timed out, cancelling owner task")
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass
        self._conn_tasks.pop(server_id, None)
        self._stop_events.pop(server_id, None)

    async def reconnect_server(self, server_id: str) -> bool:
        """重连指定服务器（线程安全）。"""
        async with self._operation_lock:
            if server_id not in self._server_configs:
                logger.warning(f"MCP server '{server_id}': no config found for reconnect")
                return False
            cfg = self._server_configs[server_id]

        for attempt in range(1, self._max_reconnect_attempts + 1):
            if attempt > 1:
                delay = self._reconnect_backoff_base * (2 ** (attempt - 2))
                logger.info(f"MCP server '{server_id}': reconnect attempt {attempt}/{self._max_reconnect_attempts} in {delay:.0f}s")
                await asyncio.sleep(delay)
            if await self._start_connection(server_id, cfg):
                logger.info(f"MCP server '{server_id}': reconnected successfully")
                return True

        logger.error(f"MCP server '{server_id}': all {self._max_reconnect_attempts} reconnect attempts failed")
        return False

    async def reconnect_all(self) -> None:
        if not self._server_configs:
            logger.warning("MCP: no server configs available for reconnect")
            return
        failed_servers = [
            sid for sid in self._server_configs
            if sid not in self._conn_tasks and sid not in self._manually_stopped
        ]
        if not failed_servers:
            logger.info("MCP: all servers are connected, nothing to reconnect")
            return
        logger.info(f"MCP: attempting reconnect for {len(failed_servers)} failed servers")
        for server_id in failed_servers:
            await self.reconnect_server(server_id)

    def _start_health_check(self) -> None:
        if self._reconnect_task and not self._reconnect_task.done():
            return
        self._reconnect_task = asyncio.create_task(self._health_check_loop())

    async def _health_check_loop(self) -> None:
        while self._connected and self._conn_tasks:
            await asyncio.sleep(self._health_check_interval)
            if not self._connected:
                break
            dead_servers: List[str] = []
            for server_id in list(self._conn_tasks.keys()):
                task = self._conn_tasks.get(server_id)
                if task is None or task.done():
                    dead_servers.append(server_id)
                    continue
                try:
                    for name in self._mcp_tool_names:
                        if name.startswith(f"mcp_{server_id}_"):
                            tool = self._registry._tools.get(name)
                            if tool and hasattr(tool, "_session"):
                                session = tool._session
                                if hasattr(session, "_read_stream"):
                                    stream = session._read_stream
                                    if hasattr(stream, "_state") and stream._state == "closed":
                                        dead_servers.append(server_id)
                                        break
                except Exception:
                    pass

            for server_id in dead_servers:
                logger.warning(f"MCP server '{server_id}': connection lost, scheduling reconnect")
                asyncio.create_task(self.reconnect_server(server_id))

            if not self._conn_tasks and self._connected:
                self._connected = False
                logger.warning("MCP: all servers disconnected")

    async def disconnect_server(self, server_id: str) -> bool:
        """断开指定服务器（线程安全）。"""
        async with self._operation_lock:
            # 标记为“用户手动停止”，避免被惰性自动连接立刻拉起
            self._manually_stopped.add(server_id)
            await self._stop_connection(server_id)
            if not self._conn_tasks and self._connected:
                self._connected = False
                if self._reconnect_task and not self._reconnect_task.done():
                    self._reconnect_task.cancel()
                    try:
                        await self._reconnect_task
                    except asyncio.CancelledError:
                        pass
                    self._reconnect_task = None

        logger.info(f"MCP server '{server_id}' disconnected")
        return True

    async def start_server(self, server_id: str) -> bool:
        """启动指定服务器（线程安全）。"""
        async with self._operation_lock:
            if server_id in self._conn_tasks:
                logger.warning(f"MCP server '{server_id}' is already running")
                return True
            if server_id not in self._server_configs:
                logger.warning(f"MCP server '{server_id}': no config found for start")
                return False
            cfg = self._server_configs[server_id]

        if await self._start_connection(server_id, cfg):
            async with self._operation_lock:
                self._connected = True
            logger.info(f"MCP server '{server_id}': started successfully")
            return True

        logger.error(f"MCP server '{server_id}': start failed")
        return False

    async def disconnect(self) -> None:
        """断开所有连接（线程安全）"""
        async with self._operation_lock:
            if self._reconnect_task and not self._reconnect_task.done():
                self._reconnect_task.cancel()
                try:
                    await self._reconnect_task
                except asyncio.CancelledError:
                    pass
                self._reconnect_task = None

            # 逐个停止持有者任务（每个任务在自己上下文里关闭连接）
            for server_id in list(self._conn_tasks.keys()):
                await self._stop_connection(server_id)

            # 兜底清理注册表残留
            self._unregister_mcp_tools()
            self._server_configs.clear()
            self._tool_wrappers.clear()
            self._mcp_tool_names.clear()
            # 全局断开是一次整体重置：清空“手动停止”标记，
            # 下次全局启用时所有 enabled server 都应能正常拉起。
            self._manually_stopped.clear()
            self._connected = False
            self._connecting = False
            logger.info("MCP disconnected")

        # 通知所有活跃的WebSocket会话MCP已断开
        try:
            from backend.modules.websocket.broadcast import broadcast_mcp_status_change
            await broadcast_mcp_status_change(connected=False)
        except Exception as e:
            logger.debug(f"Failed to broadcast MCP status change: {e}")

    def get_status(self) -> Dict[str, Any]:
        server_status = {}
        for server_id, cfg in self._server_configs.items():
            server_status[server_id] = {
                "connected": server_id in self._conn_tasks,
                "transport": cfg.transport or "auto",
                "tool_count": len([n for n in self._mcp_tool_names if n.startswith(f"mcp_{server_id}_")]),
            }
        return {
            "connected": self._connected,
            "servers": list(self._conn_tasks.keys()),
            "all_configured": list(self._server_configs.keys()),
            "server_status": server_status,
            "tool_count": len(self._mcp_tool_names),
            "tools": self._mcp_tool_names,
        }
