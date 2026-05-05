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
        self._stacks: Dict[str, AsyncExitStack] = {}
        self._connected = False
        self._connecting = False
        self._registry: Optional[ToolRegistry] = None
        self._mcp_tool_names: List[str] = []
        self._server_configs: Dict[str, McpServerConfig] = {}
        self._reconnect_task: Optional[asyncio.Task] = None
        self._health_check_interval: int = 60
        self._max_reconnect_attempts: int = 3
        self._reconnect_backoff_base: float = 5.0
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
            if cfg.enabled
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

            # Clear old wrappers before reconnecting
            self._tool_wrappers.clear()

            async def _connect_one(cfg: McpServerConfig):
                server_id = cfg.id or cfg.name or "unknown"
                try:
                    stack = await connect_mcp_server(server_id, cfg, self._registry, out_wrappers=self._tool_wrappers)
                    if stack:
                        return server_id, stack
                except Exception as exc:
                    logger.error(f"MCP server '{server_id}' connection failed: {exc}")
                return server_id, None

            results = await asyncio.gather(
                *[_connect_one(cfg) for cfg in enabled_servers],
                return_exceptions=True,
            )

            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"MCP connection error: {result}")
                    continue
                server_id, stack = result
                if stack:
                    self._stacks[server_id] = stack

            for cfg in enabled_servers:
                server_id = cfg.id or cfg.name or "unknown"
                self._server_configs[server_id] = cfg

            self._mcp_tool_names = [
                name for name in self._registry.list_tools() if name.startswith("mcp_")
            ]
            if self._stacks:
                self._connected = True
                logger.info(f"MCP connected: {len(self._stacks)} servers, {len(self._mcp_tool_names)} tools")
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

    async def reconnect_server(self, server_id: str) -> bool:
        """重连指定服务器（线程安全）"""
        async with self._operation_lock:
            if server_id not in self._server_configs:
                logger.warning(f"MCP server '{server_id}': no config found for reconnect")
                return False

            cfg = self._server_configs[server_id]

            old_stack = self._stacks.pop(server_id, None)
        if old_stack:
            try:
                await old_stack.aclose()
            except (RuntimeError, BaseExceptionGroup):
                pass

        tools_to_remove = [n for n in self._mcp_tool_names if n.startswith(f"mcp_{server_id}_")]
        for name in tools_to_remove:
            try:
                self._registry.unregister(name)
            except (KeyError, ValueError):
                pass
            self._mcp_tool_names.remove(name)
            self._tool_wrappers.pop(name, None)

            for attempt in range(1, self._max_reconnect_attempts + 1):
                delay = self._reconnect_backoff_base * (2 ** (attempt - 1))
                if attempt > 1:
                    logger.info(f"MCP server '{server_id}': reconnect attempt {attempt}/{self._max_reconnect_attempts} in {delay:.0f}s")
                    await asyncio.sleep(delay)

                try:
                    stack = await connect_mcp_server(server_id, cfg, self._registry, out_wrappers=self._tool_wrappers)
                    if stack:
                        self._stacks[server_id] = stack
                        new_tools = [n for n in self._registry.list_tools() if n.startswith(f"mcp_{server_id}_") and n not in self._mcp_tool_names]
                        self._mcp_tool_names.extend(new_tools)
                        logger.info(f"MCP server '{server_id}': reconnected successfully, {len(new_tools)} tools")
                        return True
                except Exception as exc:
                    logger.error(f"MCP server '{server_id}': reconnect attempt {attempt} failed: {exc}")

            logger.error(f"MCP server '{server_id}': all {self._max_reconnect_attempts} reconnect attempts failed")
            return False

    async def reconnect_all(self) -> None:
        if not self._server_configs:
            logger.warning("MCP: no server configs available for reconnect")
            return
        failed_servers = [sid for sid in self._server_configs if sid not in self._stacks]
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
        while self._connected and self._stacks:
            await asyncio.sleep(self._health_check_interval)
            if not self._connected:
                break
            dead_servers: List[str] = []
            for server_id, stack in list(self._stacks.items()):
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
                self._stacks.pop(server_id, None)
                asyncio.create_task(self.reconnect_server(server_id))

            if not self._stacks and self._connected:
                self._connected = False
                logger.warning("MCP: all servers disconnected")

    async def disconnect_server(self, server_id: str) -> bool:
        """断开指定服务器（线程安全）"""
        async with self._operation_lock:
            stack = self._stacks.pop(server_id, None)
        if stack:
            try:
                await stack.aclose()
            except (RuntimeError, BaseExceptionGroup):
                logger.debug(f"MCP server '{server_id}' cleanup error (can be ignored)")

        tools_to_remove = [n for n in self._mcp_tool_names if n.startswith(f"mcp_{server_id}_")]
        for name in tools_to_remove:
            try:
                self._registry.unregister(name)
            except (KeyError, ValueError):
                pass
            self._mcp_tool_names.remove(name)
            self._tool_wrappers.pop(name, None)

            if not self._stacks and self._connected:
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
        """启动指定服务器（线程安全）"""
        async with self._operation_lock:
            if server_id in self._stacks:
                logger.warning(f"MCP server '{server_id}' is already running")
                return True
            if server_id not in self._server_configs:
                logger.warning(f"MCP server '{server_id}': no config found for start")
                return False
            cfg = self._server_configs[server_id]

        try:
            stack = await connect_mcp_server(server_id, cfg, self._registry, out_wrappers=self._tool_wrappers)
            if stack:
                async with self._operation_lock:
                    self._stacks[server_id] = stack
                    new_tools = [n for n in self._registry.list_tools() if n.startswith(f"mcp_{server_id}_") and n not in self._mcp_tool_names]
                    self._mcp_tool_names.extend(new_tools)
                    self._connected = True
                logger.info(f"MCP server '{server_id}': started successfully, {len(new_tools)} tools")
                return True
        except Exception as exc:
            logger.error(f"MCP server '{server_id}': start failed: {exc}")
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

            self._unregister_mcp_tools()

            for name, stack in self._stacks.items():
                try:
                    await stack.aclose()
                except (RuntimeError, BaseExceptionGroup):
                    logger.debug(f"MCP server '{name}' cleanup error (can be ignored)")
            self._stacks.clear()
            self._server_configs.clear()
            self._tool_wrappers.clear()
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
                "connected": server_id in self._stacks,
                "transport": cfg.transport or "auto",
                "tool_count": len([n for n in self._mcp_tool_names if n.startswith(f"mcp_{server_id}_")]),
            }
        return {
            "connected": self._connected,
            "servers": list(self._stacks.keys()),
            "all_configured": list(self._server_configs.keys()),
            "server_status": server_status,
            "tool_count": len(self._mcp_tool_names),
            "tools": self._mcp_tool_names,
        }
