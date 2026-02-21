"""Spawn Tool - 生成子 Agent 工具"""

from typing import Any

from backend.modules.tools.base import Tool


class SpawnTool(Tool):
    """
    生成子 Agent 工具
    
    用于创建后台子 Agent 执行复杂或耗时的任务。
    子 Agent 会独立运行，完成后向主 Agent 报告结果。
    """
    
    def __init__(self, manager):
        """
        初始化 SpawnTool
        
        Args:
            manager: SubagentManager 实例
        """
        self._manager = manager
        self._session_id = None
    
    def set_context(self, session_id: str) -> None:
        """设置上下文（会话 ID）"""
        self._session_id = session_id
    
    @property
    def name(self) -> str:
        return "spawn"
    
    @property
    def description(self) -> str:
        return (
            "Spawn background agent for complex or time-consuming tasks. "
            "Use when task requires multiple steps, tools, or takes significant time."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "Task description for the background agent",
                },
                "label": {
                    "type": "string",
                    "description": "Short label for task display (optional)",
                },
            },
            "required": ["task"],
        }
    
    async def execute(self, task: str, label: str | None = None, **kwargs: Any) -> str:
        """
        执行工具：生成子 Agent
        
        Args:
            task: 任务描述
            label: 任务标签（可选）
            
        Returns:
            str: 状态消息
        """
        # 创建任务
        task_id = self._manager.create_task(
            label=label or task[:30] + ("..." if len(task) > 30 else ""),
            message=task,
            session_id=self._session_id,
        )
        
        # 异步执行任务
        await self._manager.execute_task(task_id)
        
        display_label = label or task[:30] + ("..." if len(task) > 30 else "")
        return f"子 Agent [{display_label}] 已启动 (ID: {task_id})。完成后我会通知你。"
