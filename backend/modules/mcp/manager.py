"""MCP 客户端管理器：连接生命周期、工具注册与健康检查。"""

import asyncio
from contextlib import AsyncExitStack
from typing import Any, Dict, List, Optional

from loguru import logger

from backend.modules.config.schema import McpServerConfig
from backend.modules.tools.base import Tool
from backend.modules.tools.registry import ToolRegistry


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
            # 经门面调用连接函数：测试与文档都以 backend.modules.mcp.client 为入口，
            # 在该模块上替换 connect_mcp_server 应当生效。延迟导入避免循环依赖。
            from backend.modules.mcp import client as client_facade

            stack = await client_facade.connect_mcp_server(
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
