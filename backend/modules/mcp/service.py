"""MCP 服务层：统一封装客户端管理与业务操作。"""

import asyncio
from typing import Any, Dict, List, Optional
from loguru import logger

from backend.modules.config.schema import McpServerConfig, McpRegistryConfig
from backend.modules.mcp.client import McpClientManager
from backend.modules.mcp.validators import McpConfigValidator
from backend.modules.tools.registry import ToolRegistry


class McpServiceError(Exception):
    """MCP服务层异常基类"""
    pass


class McpConnectionError(McpServiceError):
    """MCP连接异常"""
    pass


class McpValidationError(McpServiceError):
    """MCP配置验证异常"""
    pass


class McpService:
    """MCP 服务层：封装客户端管理、错误处理与后台任务。"""

    def __init__(self, tool_registry: Optional[ToolRegistry] = None):
        self._manager = McpClientManager.get_instance()
        self._validator = McpConfigValidator()
        self._background_tasks: Dict[str, asyncio.Task] = {}

        if tool_registry:
            self._manager.set_registry(tool_registry)

    def set_registry(self, registry: ToolRegistry) -> None:
        """设置工具注册表"""
        self._manager.set_registry(registry)

    async def connect_servers(
        self,
        servers: List[McpServerConfig],
        background: bool = False
    ) -> Dict[str, Any]:
        """连接MCP服务器"""
        # 验证配置
        for server in servers:
            errors = self._validator.validate_server(server)
            if errors:
                raise McpValidationError(f"Server '{server.name}' validation failed: {errors}")

        if background:
            task_id = f"connect_{id(servers)}"
            task = asyncio.create_task(self._manager.connect(servers))
            self._background_tasks[task_id] = task

            # 清理完成的任务
            def cleanup(t):
                self._background_tasks.pop(task_id, None)
                if t.exception():
                    logger.error(f"Background connect task failed: {t.exception()}")

            task.add_done_callback(cleanup)

            return {
                "status": "connecting",
                "task_id": task_id,
                "server_count": len(servers)
            }
        else:
            await self._manager.connect(servers)
            return {
                "status": "connected",
                "server_count": len(servers),
                "connected_servers": list(self._manager._conn_tasks.keys())
            }

    async def disconnect_all(self) -> None:
        """断开所有MCP服务器连接"""
        await self._manager.disconnect()

        # 取消所有后台任务
        for task_id, task in list(self._background_tasks.items()):
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._background_tasks.clear()

    async def reconnect_server(self, server_id: str) -> bool:
        """重连指定服务器"""
        try:
            return await self._manager.reconnect_server(server_id)
        except Exception as e:
            logger.error(f"Failed to reconnect server '{server_id}': {e}")
            raise McpConnectionError(f"Reconnect failed: {e}")

    async def reconnect_all(self) -> Dict[str, bool]:
        """重连所有失败的服务器"""
        await self._manager.reconnect_all()
        status = self._manager.get_status()

        results = {}
        for server_id in status["all_configured"]:
            results[server_id] = server_id in status["servers"]

        return results

    async def start_server(self, server_id: str) -> bool:
        """启动指定服务器"""
        try:
            return await self._manager.start_server(server_id)
        except Exception as e:
            logger.error(f"Failed to start server '{server_id}': {e}")
            raise McpConnectionError(f"Start failed: {e}")

    async def stop_server(self, server_id: str) -> bool:
        """停止指定服务器"""
        try:
            return await self._manager.disconnect_server(server_id)
        except Exception as e:
            logger.error(f"Failed to stop server '{server_id}': {e}")
            raise McpConnectionError(f"Stop failed: {e}")

    def get_status(self) -> Dict[str, Any]:
        """获取MCP状态"""
        status = self._manager.get_status()

        # 添加后台任务状态
        status["background_tasks"] = {
            task_id: {
                "done": task.done(),
                "cancelled": task.cancelled()
            }
            for task_id, task in self._background_tasks.items()
        }

        return status

    def get_server_status(self, server_id: str) -> Optional[Dict[str, Any]]:
        """获取指定服务器状态"""
        status = self._manager.get_status()
        server_status = status.get("server_status", {}).get(server_id)

        if server_status is None:
            return None

        # 添加工具列表
        all_tools = status.get("tools", [])
        server_tools = [
            t for t in all_tools
            if t.startswith(f"mcp__{server_id}__") or t.startswith(f"mcp_{server_id}_")
        ]
        server_status["tools"] = server_tools

        return server_status

    def sync_to_registry(self, registry: ToolRegistry) -> int:
        """同步MCP工具到新的注册表"""
        return self._manager.sync_to_registry_sync(registry)

    async def sync_to_registry_async(self, registry: ToolRegistry) -> int:
        """同步MCP工具到新的注册表"""
        return await self._manager.sync_to_registry(registry)

    @property
    def connected(self) -> bool:
        """是否已连接"""
        return self._manager.connected

    async def test_server(self, config: McpServerConfig) -> Dict[str, Any]:
        """测试服务器连接"""
        # 验证配置
        errors = self._validator.validate_server(config)
        if errors:
            return {
                "success": False,
                "message": f"Validation failed: {', '.join(errors)}"
            }

        try:
            from backend.modules.mcp.client import test_mcp_server
            result = await test_mcp_server(config)
            return result
        except ImportError:
            return {
                "success": False,
                "message": "mcp package not installed, run: pip install mcp"
            }
        except Exception as e:
            logger.error(f"Test server failed: {e}")
            return {
                "success": False,
                "message": f"Test failed: {type(e).__name__}: {e}"
            }

    def update_server_config(self, server_id: str, config: McpServerConfig) -> None:
        """更新服务器配置"""
        self._manager._server_configs[server_id] = config

    async def cleanup(self) -> None:
        """清理资源"""
        await self.disconnect_all()
        logger.info("MCP service cleaned up")
