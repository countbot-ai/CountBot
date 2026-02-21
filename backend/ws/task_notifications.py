"""WebSocket 任务状态更新推送

提供后台任务状态的实时推送功能：
- 任务创建通知
- 任务状态更新通知
- 任务进度更新通知
- 任务完成/失败通知
"""

import asyncio
from typing import Any

from loguru import logger

from backend.ws.connection import connection_manager, ServerMessage


# ============================================================================
# Task Notification Messages
# ============================================================================


class TaskCreatedMessage(ServerMessage):
    """任务创建通知"""

    type: str = "task_created"
    task_id: str
    label: str
    timestamp: float


class TaskStatusMessage(ServerMessage):
    """任务状态更新通知"""

    type: str = "task_status"
    task_id: str
    status: str  # running, completed, failed
    progress: int  # 0-100
    message: str | None = None


class TaskProgressMessage(ServerMessage):
    """任务进度更新通知"""

    type: str = "task_progress"
    task_id: str
    progress: int  # 0-100
    current: int | None = None
    total: int | None = None
    message: str | None = None


class TaskCompleteMessage(ServerMessage):
    """任务完成通知"""

    type: str = "task_complete"
    task_id: str
    result: str | None = None
    duration_ms: float


class TaskFailedMessage(ServerMessage):
    """任务失败通知"""

    type: str = "task_failed"
    task_id: str
    error: str
    duration_ms: float


class TaskLogMessage(ServerMessage):
    """任务日志消息"""

    type: str = "task_log"
    task_id: str
    level: str  # info, warning, error
    message: str
    timestamp: float


# ============================================================================
# Task Notification Handler
# ============================================================================


class TaskNotificationHandler:
    """任务通知处理器

    管理后台任务的状态通知，支持：
    - 状态更新
    - 进度跟踪
    - 日志推送
    - 完成/失败通知
    """

    def __init__(self, task_id: str, label: str):
        """初始化任务通知处理器

        Args:
            task_id: 任务 ID
            label: 任务标签
        """
        self.task_id = task_id
        self.label = label
        self.status = "running"
        self.progress = 0
        self.start_time = asyncio.get_event_loop().time()

    async def notify_created(self) -> None:
        """通知任务创建"""
        logger.info(f"任务创建: {self.task_id} - {self.label}")

        message = TaskCreatedMessage(
            task_id=self.task_id,
            label=self.label,
            timestamp=self.start_time,
        )

        await connection_manager.broadcast(message)

    async def notify_status(
        self, status: str, progress: int | None = None, message: str | None = None
    ) -> None:
        """通知任务状态更新

        Args:
            status: 任务状态 (running, completed, failed)
            progress: 进度百分比 (0-100)
            message: 状态消息（可选）
        """
        self.status = status
        if progress is not None:
            self.progress = max(0, min(100, progress))

        logger.info(f"任务状态更新: {self.task_id} - {status} ({self.progress}%)")

        notification = TaskStatusMessage(
            task_id=self.task_id,
            status=status,
            progress=self.progress,
            message=message,
        )

        await connection_manager.broadcast(notification)

    async def notify_progress(
        self,
        progress: int,
        current: int | None = None,
        total: int | None = None,
        message: str | None = None,
    ) -> None:
        """通知任务进度更新

        Args:
            progress: 进度百分比 (0-100)
            current: 当前进度值（可选）
            total: 总进度值（可选）
            message: 进度消息（可选）
        """
        self.progress = max(0, min(100, progress))

        logger.debug(f"任务进度: {self.task_id} - {self.progress}%")

        notification = TaskProgressMessage(
            task_id=self.task_id,
            progress=self.progress,
            current=current,
            total=total,
            message=message,
        )

        await connection_manager.broadcast(notification)

    async def notify_complete(self, result: str | None = None) -> None:
        """通知任务完成

        Args:
            result: 任务结果（可选）
        """
        self.status = "completed"
        self.progress = 100

        duration_ms = (asyncio.get_event_loop().time() - self.start_time) * 1000

        logger.info(
            f"任务完成: {self.task_id} (耗时 {duration_ms:.2f}ms)"
        )

        message = TaskCompleteMessage(
            task_id=self.task_id,
            result=result,
            duration_ms=duration_ms,
        )

        await connection_manager.broadcast(message)

    async def notify_failed(self, error: str) -> None:
        """通知任务失败

        Args:
            error: 错误信息
        """
        self.status = "failed"

        duration_ms = (asyncio.get_event_loop().time() - self.start_time) * 1000

        logger.error(
            f"任务失败: {self.task_id} - {error} (耗时 {duration_ms:.2f}ms)"
        )

        message = TaskFailedMessage(
            task_id=self.task_id,
            error=error,
            duration_ms=duration_ms,
        )

        await connection_manager.broadcast(message)

    async def log(self, level: str, message: str) -> None:
        """发送任务日志

        Args:
            level: 日志级别 (info, warning, error)
            message: 日志消息
        """
        logger.log(level.upper(), f"[Task {self.task_id}] {message}")

        notification = TaskLogMessage(
            task_id=self.task_id,
            level=level,
            message=message,
            timestamp=asyncio.get_event_loop().time(),
        )

        await connection_manager.broadcast(notification)

    def get_duration_ms(self) -> float:
        """获取任务执行时长（毫秒）

        Returns:
            float: 执行时长
        """
        return (asyncio.get_event_loop().time() - self.start_time) * 1000


# ============================================================================
# Task Manager Integration
# ============================================================================


class TaskNotificationManager:
    """任务通知管理器

    管理所有任务的通知处理器。
    """

    def __init__(self):
        """初始化任务通知管理器"""
        self.handlers: dict[str, TaskNotificationHandler] = {}

    def create_handler(self, task_id: str, label: str) -> TaskNotificationHandler:
        """创建任务通知处理器

        Args:
            task_id: 任务 ID
            label: 任务标签

        Returns:
            TaskNotificationHandler: 任务通知处理器
        """
        handler = TaskNotificationHandler(task_id, label)
        self.handlers[task_id] = handler
        return handler

    def get_handler(self, task_id: str) -> TaskNotificationHandler | None:
        """获取任务通知处理器

        Args:
            task_id: 任务 ID

        Returns:
            TaskNotificationHandler | None: 任务通知处理器
        """
        return self.handlers.get(task_id)

    def remove_handler(self, task_id: str) -> None:
        """移除任务通知处理器

        Args:
            task_id: 任务 ID
        """
        if task_id in self.handlers:
            del self.handlers[task_id]

    def get_all_handlers(self) -> list[TaskNotificationHandler]:
        """获取所有任务通知处理器

        Returns:
            list[TaskNotificationHandler]: 任务通知处理器列表
        """
        return list(self.handlers.values())

    async def notify_all_tasks_status(self) -> None:
        """通知所有任务的状态"""
        for handler in self.handlers.values():
            await handler.notify_status(handler.status, handler.progress)


# ============================================================================
# Global Task Notification Manager
# ============================================================================

# 全局任务通知管理器实例
task_notification_manager = TaskNotificationManager()


# ============================================================================
# Helper Functions
# ============================================================================


async def notify_task_created(task_id: str, label: str) -> TaskNotificationHandler:
    """通知任务创建（便捷函数）

    Args:
        task_id: 任务 ID
        label: 任务标签

    Returns:
        TaskNotificationHandler: 任务通知处理器
    """
    handler = task_notification_manager.create_handler(task_id, label)
    await handler.notify_created()
    return handler


async def notify_task_status(
    task_id: str,
    status: str,
    progress: int | None = None,
    message: str | None = None,
) -> None:
    """通知任务状态更新（便捷函数）

    Args:
        task_id: 任务 ID
        status: 任务状态
        progress: 进度百分比（可选）
        message: 状态消息（可选）
    """
    handler = task_notification_manager.get_handler(task_id)
    if handler:
        await handler.notify_status(status, progress, message)


async def notify_task_progress(
    task_id: str,
    progress: int,
    current: int | None = None,
    total: int | None = None,
    message: str | None = None,
) -> None:
    """通知任务进度更新（便捷函数）

    Args:
        task_id: 任务 ID
        progress: 进度百分比
        current: 当前进度值（可选）
        total: 总进度值（可选）
        message: 进度消息（可选）
    """
    handler = task_notification_manager.get_handler(task_id)
    if handler:
        await handler.notify_progress(progress, current, total, message)


async def notify_task_complete(task_id: str, result: str | None = None) -> None:
    """通知任务完成（便捷函数）

    Args:
        task_id: 任务 ID
        result: 任务结果（可选）
    """
    handler = task_notification_manager.get_handler(task_id)
    if handler:
        await handler.notify_complete(result)
        task_notification_manager.remove_handler(task_id)


async def notify_task_failed(task_id: str, error: str) -> None:
    """通知任务失败（便捷函数）

    Args:
        task_id: 任务 ID
        error: 错误信息
    """
    handler = task_notification_manager.get_handler(task_id)
    if handler:
        await handler.notify_failed(error)
        task_notification_manager.remove_handler(task_id)


async def log_task_message(task_id: str, level: str, message: str) -> None:
    """发送任务日志（便捷函数）

    Args:
        task_id: 任务 ID
        level: 日志级别
        message: 日志消息
    """
    handler = task_notification_manager.get_handler(task_id)
    if handler:
        await handler.log(level, message)
