"""actor 专用结构化结果提交工具。"""

import json
from typing import Any, Dict

from backend.modules.tools.base import Tool
from backend.modules.workflow.results import result_submission
from backend.modules.tools.execution import ExecutionState, ToolResult


class SubmitResultTool(Tool):
    def __init__(self, schema: Dict[str, Any], on_submit) -> None:
        self._schema = schema
        self._on_submit = on_submit

    @property
    def name(self) -> str:
        return "submit_result"

    @property
    def description(self) -> str:
        return "Submit the final structured answer for this ask. Call exactly once."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {"result": self._schema},
            "required": ["result"],
            "additionalProperties": False,
        }

    async def execute_outcome(self, **kwargs: Any):
        result = result_submission(kwargs.get("result"), self._schema)
        if result.state is ExecutionState.SUCCEEDED:
            self._on_submit(kwargs["result"])
            result = ToolResult(
                state=result.state,
                display_text="Structured result accepted.",
                output=json.dumps(kwargs["result"], ensure_ascii=False),
            )
        return result
