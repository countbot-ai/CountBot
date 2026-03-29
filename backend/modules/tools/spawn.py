"""Spawn Tool - 生成子 Agent 工具"""

import asyncio
from typing import Any, Dict, Optional

from loguru import logger

from backend.database import SessionLocal
from backend.models.session import Session
from backend.modules.config.loader import config_loader
from backend.modules.session.runtime_config import (
    build_session_model_override,
    resolve_session_runtime_config,
)
from backend.modules.tools.base import Tool


class SpawnTool(Tool):
    """生成子 Agent，等待其完成并将真实结果返回给主代理。"""

    def __init__(self, manager, config_loader=None):
        self._manager = manager
        self._session_id = None
        self._config_loader = config_loader
        self._cancel_token = None

    def set_context(self, session_id: str) -> None:
        self._session_id = session_id

    def set_session_id(self, session_id: Optional[str]) -> None:
        """兼容 ToolRegistry 的会话注入接口。"""
        self._session_id = session_id

    def set_cancel_token(self, cancel_token) -> None:
        """设置取消令牌"""
        self._cancel_token = cancel_token

    @property
    def name(self) -> str:
        return "spawn"

    @property
    def description(self) -> str:
        return "Run a sub-agent and return its final result."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "Sub-agent task.",
                },
                "label": {
                    "type": "string",
                    "description": "Optional label.",
                },
            },
            "required": ["task"],
        }

    def _get_timeout(self) -> int:
        """获取子代理超时时间（秒）"""
        if self._config_loader:
            try:
                config = getattr(self._config_loader, "config", None)
                if config is not None:
                    return config.security.subagent_timeout
            except Exception:
                pass
        try:
            config = getattr(config_loader, "config", None)
            if config is not None:
                return config.security.subagent_timeout
        except Exception:
            pass
        # 默认 1200 秒（20 分钟）
        return 1200

    def _load_session_model_override(self) -> Optional[Dict[str, Any]]:
        """为当前会话加载模型覆盖，用于让子代理继承会话级自定义模型。"""
        if not self._session_id:
            return None

        try:
            with SessionLocal() as session:
                db_session = session.get(Session, self._session_id)
                if not db_session or not db_session.use_custom_config:
                    return None

                runtime_config = resolve_session_runtime_config(config_loader.config, db_session)
                model_override = build_session_model_override(runtime_config)
                if model_override:
                    logger.info(
                        "Spawn tool inherited session model config: {}/{} (session={})",
                        runtime_config.provider_name,
                        runtime_config.model_name,
                        self._session_id,
                    )
                return model_override
        except Exception as exc:
            logger.warning(
                f"Failed to load session model override for spawn tool: {exc}"
            )
            return None

    async def execute(self, task: str, label: Optional[str] = None, **kwargs: Any) -> str:
        display_label = label or task[:30] + ("..." if len(task) > 30 else "")
        model_override = self._load_session_model_override()

        task_id = self._manager.create_task(
            label=display_label,
            message=task,
            session_id=self._session_id,
            model_override=model_override,
            cancel_token=self._cancel_token,
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
