"""模型可见的 Dynamic Workflow 工具；只接受受限 JSON AST，需用户确认。"""

import uuid
from typing import Any, Dict, Optional

from backend.modules.tools.base import Tool
from backend.modules.tools.execution import (
    ErrorCategory,
    ExecutionState,
    SideEffectState,
    ToolResult,
)
from backend.modules.workflow.service import DynamicWorkflowService


class DynamicWorkflowTool(Tool):
    def __init__(self, service: DynamicWorkflowService, *, owner_id=None,
                 session_id=None, workspace=None, user=None) -> None:
        self.service = service
        self.owner_id = owner_id
        self.session_id = session_id
        self.workspace = workspace
        self.user = user

    @property
    def name(self) -> str:
        return "dynamic_workflow_run"

    @property
    def description(self) -> str:
        return (
            "Compile and run a bounded Dynamic Workflow JSON program. "
            "The user must have explicitly approved this workflow; "
            "pass confirmed=true only after showing the plan to the user "
            "and receiving their approval."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "program": {
                    "type": "object",
                    "description": "Versioned JSON AST with agents, bounded control flow and ask statements.",
                },
                "run_id": {"type": "string", "description": "Optional id for a new run."},
                "confirmed": {
                    "type": "boolean",
                    "description": "Must be true only after the user has approved the plan.",
                    "default": False,
                },
            },
            "required": ["program"],
            "additionalProperties": False,
        }

    async def execute_outcome(self, **kwargs: Any) -> ToolResult:
        program = kwargs.get("program")
        confirmed = bool(kwargs.get("confirmed", False))
        run_id = kwargs.get("run_id") or f"dwf-{uuid.uuid4().hex[:12]}"
        if self.workspace is None:
            return ToolResult.failure(
                ErrorCategory.VALIDATION,
                "Dynamic Workflow requires a workspace.",
                side_effect_state=SideEffectState.NOT_ATTEMPTED,
            )
        result = await self.service.start(
            run_id=run_id,
            owner_id=self.owner_id,
            session_id=self.session_id,
            workspace=str(self.workspace),
            program=program,
            user=self.user,
            confirmed=confirmed,
        )
        if result.state is ExecutionState.SUCCEEDED:
            return ToolResult.success({
                "run_id": run_id,
                "status": "completed",
                "result": result.output,
            })
        return result
