"""WebSocket 工具调用通知

提供工具调用的实时通知功能：
- 工具调用开始通知
- 工具执行进度通知
- 工具执行结果通知
- 工具执行错误通知
"""

import asyncio
import time
from typing import Any, Dict, List, Literal, Optional, Tuple

from loguru import logger
from backend.modules.tools.execution import (
    CanonicalToolExecutionResult,
    ExecutionState,
    ToolExecutionInProgress,
    ToolExecutionRejected,
)

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
    arguments: Dict[str, Any]
    timestamp: float


class ToolProgressMessage(ServerMessage):
    """工具执行进度通知"""

    type: str = "tool_progress"
    tool: str
    progress: int  # 0-100
    message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    timestamp: float


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

    async def notify_start(self, arguments: Dict[str, Any]) -> None:
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
        self,
        progress: int,
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
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
            details=details,
            timestamp=time.time(),
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
            f"工具执行未成功: {self.tool_name} - {error} (耗时 {duration_ms:.2f}ms)"
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
    arguments: Dict[str, Any],
    executor: callable,
) -> CanonicalToolExecutionResult:
    """依据 Registry 结构化结果发送完成、错误或进度通知。

    Args:
        session_id: 会话 ID
        tool_name: 工具名称
        arguments: 工具参数
        executor: 工具执行函数

    Returns:
        CanonicalToolExecutionResult: 物理尝试终态或进行中准入结果

    Raises:
        Exception: 执行边界意外上抛
    """
    handler = ToolNotificationHandler(session_id, tool_name)

    try:
        # 通知开始
        await handler.notify_start(arguments)

        # executor 返回权威状态；展示文本只进入对应通知。
        outcome = await executor(tool_name, arguments)
        if isinstance(outcome, ToolExecutionInProgress):
            await handler.notify_progress(0, outcome.display_text)
            return outcome
        if isinstance(outcome, ToolExecutionRejected):
            await handler.notify_error(outcome.display_text)
            return outcome
        if outcome.state is ExecutionState.SUCCEEDED:
            await handler.notify_complete(outcome.display_text)
        else:
            error_text = outcome.display_text
            if outcome.state is ExecutionState.UNKNOWN_OUTCOME:
                error_text = "Tool outcome is unknown; side effects may have occurred. " + error_text
            await handler.notify_error(error_text)

        return outcome

    except Exception as e:
        # 边界异常没有可消费的结构化终态，按错误通知并继续抛出。
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
        self.handlers: Dict[str, ToolNotificationHandler] = {}

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

    def get_handler(self, tool_name: str) -> Optional[ToolNotificationHandler]:
        """获取工具通知处理器

        Args:
            tool_name: 工具名称

        Returns:
            ToolNotificationHandler | None: 工具通知处理器
        """
        return self.handlers.get(tool_name)

    def get_all_handlers(self) -> List[ToolNotificationHandler]:
        """获取所有工具通知处理器

        Returns:
            List[ToolNotificationHandler]: 工具通知处理器列表
        """
        return list(self.handlers.values())

    async def notify_batch_start(self, tools: List[Tuple[str, Dict[str, Any]]]) -> None:
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
    arguments: Dict[str, Any],
    result: Optional[str] = None,
    error: Optional[str] = None,
    phase: Literal["start", "success", "non_success"] = "start",
) -> None:
    """发送工具执行通知（便捷函数）

    Args:
        session_id: 会话 ID
        tool_name: 工具名称
        arguments: 工具参数
        result: 执行结果（可选）
        error: 错误信息（可选）
        phase: 上游依据结构化状态选定的通知阶段
    """
    if phase == "non_success":
        # 错误通知
        await send_error(session_id, f"Tool '{tool_name}' did not succeed: {error or ''}", "TOOL_ERROR")
    elif phase == "success":
        # 仅发送结果（tool_call 已在开始时发送，避免重复）
        await send_tool_result(session_id, tool_name, result or "")
    else:
        # 工具开始执行：发送调用通知
        await send_tool_call(session_id, tool_name, arguments)


async def notify_tool_progress(
    session_id: str,
    tool_name: str,
    progress: int,
    message: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """发送工具执行进度通知（便捷函数）。"""

    notification = ToolProgressMessage(
        tool=tool_name,
        progress=max(0, min(100, int(progress))),
        message=message,
        details=details,
        timestamp=time.time(),
    )
    await connection_manager.send_to_session(session_id, notification)
