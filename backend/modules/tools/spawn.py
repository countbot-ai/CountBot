"""Spawn Tool - 生成子 Agent 工具"""

import asyncio
from typing import Any, Dict, Optional

from backend.modules.tools.base import Tool


class SpawnTool(Tool):
    """生成子 Agent，等待其完成并将真实结果返回给主代理。"""

    def __init__(self, manager, config_loader=None):
        self._manager = manager
        self._session_id = None
        self._config_loader = config_loader

    def set_context(self, session_id: str) -> None:
        self._session_id = session_id

    @property
    def name(self) -> str:
        return "spawn"

    @property
    def description(self) -> str:
        return (
            "Spawn a sub-agent to handle a complex or time-consuming task. "
            "The sub-agent runs to completion and returns its result here."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "Task description for the sub-agent",
                },
                "label": {
                    "type": "string",
                    "description": "Short display label (optional)",
                },
            },
            "required": ["task"],
        }

    def _get_timeout(self) -> int:
        """获取子代理超时时间（秒）"""
        if self._config_loader:
            try:
                config = self._config_loader.get_config()
                return config.security.subagent_timeout
            except Exception:
                pass
        # 默认 600 秒（10 分钟）
        return 600

    async def execute(self, task: str, label: Optional[str] = None, **kwargs: Any) -> str:
        display_label = label or task[:30] + ("..." if len(task) > 30 else "")

        task_id = self._manager.create_task(
            label=display_label,
            message=task,
            session_id=self._session_id,
        )

        try:
            from backend.ws.task_notifications import task_notification_manager

            handler = task_notification_manager.create_handler(
                task_id, display_label, session_id=self._session_id
            )
            self._manager.tasks[task_id].notification_handler = handler
            await handler.notify_created()
        except Exception:
            pass

        # Start task in background so WebSocket updates can flow while we wait
        await self._manager.execute_task(task_id)

        sub_task = self._manager.tasks[task_id]
        timeout = self._get_timeout()
        try:
            await asyncio.wait_for(sub_task.done_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            return f"子 Agent [{display_label}] 超时 (ID: {task_id})，任务仍在后台运行。"

        if sub_task.error:
            return f"子 Agent [{display_label}] 失败 (ID: {task_id}): {sub_task.error}"

        result_text = sub_task.result or ""
        return f"子 Agent [{display_label}] 已完成 (ID: {task_id})。\n\n{result_text}"
