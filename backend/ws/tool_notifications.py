"""WebSocket 工具调用通知

提供工具调用的实时通知功能：
- 工具调用开始通知
- 工具执行进度通知
- 工具执行结果通知
- 工具执行错误通知
"""

import asyncio
import time
from typing import Any

from loguru import logger

from backend.ws.connection import (
    connection_manager,
    send_tool_call,
    send_tool_result,
    send_error,
    ServerMessage,
)


# ============================================================================
# Tool Notification Messages
# ============================================================================


class ToolStartMessage(ServerMessage):
    """工具开始执行通知"""

    type: str = "tool_start"
    tool: str
    arguments: dict[str, Any]
    timestamp: float


class ToolProgressMessage(ServerMessage):
    """工具执行进度通知"""

    type: str = "tool_progress"
    tool: str
    progress: int  # 0-100
    message: str | None = None


class ToolCompleteMessage(ServerMessage):
    """工具执行完成通知"""

    type: str = "tool_complete"
    tool: str
    result: str
    duration_ms: float


class ToolErrorMessage(ServerMessage):
    """工具执行错误通知"""

    type: str = "tool_error"
    tool: str
    error: str
    duration_ms: float


# ============================================================================
# Tool Notification Handler
# ============================================================================


class ToolNotificationHandler:
    """工具通知处理器

    管理工具调用的通知，支持：
    - 开始/完成/错误通知
    - 进度跟踪
    - 执行时间统计
    """

    def __init__(self, session_id: str, tool_name: str):
        """初始化工具通知处理器

        Args:
            session_id: 会话 ID
            tool_name: 工具名称
        """
        self.session_id = session_id
        self.tool_name = tool_name
        self.start_time = time.time()
        self.progress = 0

    async def notify_start(self, arguments: dict[str, Any]) -> None:
        """通知工具开始执行

        Args:
            arguments: 工具参数
        """
        logger.info(f"工具开始执行: {self.tool_name}")

        message = ToolStartMessage(
            tool=self.tool_name,
            arguments=arguments,
            timestamp=self.start_time,
        )

        await connection_manager.send_to_session(self.session_id, message)

    async def notify_progress(
        self, progress: int, message: str | None = None
    ) -> None:
        """通知工具执行进度

        Args:
            progress: 进度百分比 (0-100)
            message: 进度消息（可选）
        """
        self.progress = max(0, min(100, progress))

        logger.debug(f"工具执行进度: {self.tool_name} - {self.progress}%")

        notification = ToolProgressMessage(
            tool=self.tool_name,
            progress=self.progress,
            message=message,
        )

        await connection_manager.send_to_session(self.session_id, notification)

    async def notify_complete(self, result: str) -> None:
        """通知工具执行完成

        Args:
            result: 执行结果
        """
        duration_ms = (time.time() - self.start_time) * 1000

        logger.info(
            f"工具执行完成: {self.tool_name} (耗时 {duration_ms:.2f}ms)"
        )

        message = ToolCompleteMessage(
            tool=self.tool_name,
            result=result,
            duration_ms=duration_ms,
        )

        await connection_manager.send_to_session(self.session_id, message)

    async def notify_error(self, error: str) -> None:
        """通知工具执行错误

        Args:
            error: 错误信息
        """
        duration_ms = (time.time() - self.start_time) * 1000

        logger.error(
            f"工具执行失败: {self.tool_name} - {error} (耗时 {duration_ms:.2f}ms)"
        )

        message = ToolErrorMessage(
            tool=self.tool_name,
            error=error,
            duration_ms=duration_ms,
        )

        await connection_manager.send_to_session(self.session_id, message)

    def get_duration_ms(self) -> float:
        """获取执行时长（毫秒）

        Returns:
            float: 执行时长
        """
        return (time.time() - self.start_time) * 1000


# ============================================================================
# Tool Execution Wrapper
# ============================================================================


async def execute_tool_with_notifications(
    session_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    executor: callable,
) -> str:
    """执行工具并发送通知

    Args:
        session_id: 会话 ID
        tool_name: 工具名称
        arguments: 工具参数
        executor: 工具执行函数

    Returns:
        str: 执行结果

    Raises:
        Exception: 工具执行失败
    """
    handler = ToolNotificationHandler(session_id, tool_name)

    try:
        # 通知开始
        await handler.notify_start(arguments)

        # 执行工具
        result = await executor(tool_name, arguments)

        # 通知完成
        await handler.notify_complete(result)

        return result

    except Exception as e:
        # 通知错误
        await handler.notify_error(str(e))
        raise


# ============================================================================
# Batch Tool Notifications
# ============================================================================


class BatchToolNotificationHandler:
    """批量工具通知处理器

    用于管理多个工具的并发执行通知。
    """

    def __init__(self, session_id: str):
        """初始化批量工具通知处理器

        Args:
            session_id: 会话 ID
        """
        self.session_id = session_id
        self.handlers: dict[str, ToolNotificationHandler] = {}

    def create_handler(self, tool_name: str) -> ToolNotificationHandler:
        """创建工具通知处理器

        Args:
            tool_name: 工具名称

        Returns:
            ToolNotificationHandler: 工具通知处理器
        """
        handler = ToolNotificationHandler(self.session_id, tool_name)
        self.handlers[tool_name] = handler
        return handler

    def get_handler(self, tool_name: str) -> ToolNotificationHandler | None:
        """获取工具通知处理器

        Args:
            tool_name: 工具名称

        Returns:
            ToolNotificationHandler | None: 工具通知处理器
        """
        return self.handlers.get(tool_name)

    def get_all_handlers(self) -> list[ToolNotificationHandler]:
        """获取所有工具通知处理器

        Returns:
            list[ToolNotificationHandler]: 工具通知处理器列表
        """
        return list(self.handlers.values())

    async def notify_batch_start(self, tools: list[tuple[str, dict[str, Any]]]) -> None:
        """通知批量工具开始执行

        Args:
            tools: 工具列表 [(tool_name, arguments), ...]
        """
        for tool_name, arguments in tools:
            handler = self.create_handler(tool_name)
            await handler.notify_start(arguments)

    async def notify_batch_complete(self) -> None:
        """通知批量工具执行完成"""
        message = ServerMessage(type="batch_tools_complete")
        await connection_manager.send_to_session(self.session_id, message)


# ============================================================================
# Helper Functions
# ============================================================================


async def notify_tool_execution(
    session_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    result: str | None = None,
    error: str | None = None,
) -> None:
    """发送工具执行通知（便捷函数）

    Args:
        session_id: 会话 ID
        tool_name: 工具名称
        arguments: 工具参数
        result: 执行结果（可选）
        error: 错误信息（可选）
    """
    if error:
        # 发送错误通知
        await send_error(session_id, f"Tool '{tool_name}' failed: {error}", "TOOL_ERROR")
    elif result:
        # 发送调用和结果通知
        await send_tool_call(session_id, tool_name, arguments)
        await send_tool_result(session_id, tool_name, result)
    else:
        # 只发送调用通知
        await send_tool_call(session_id, tool_name, arguments)
