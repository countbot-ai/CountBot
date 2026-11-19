"""Dynamic Workflow 的 ask 结果：结构化值与 ToolResult 展示文本分离。"""

import json
from dataclasses import dataclass
from typing import Any, Optional

from backend.modules.tools.execution import ExecutionState, ToolResult


@dataclass(frozen=True)
class AskResult(ToolResult):
    """ToolResult 仍输出文本；value 是已经 schema 校验的结构化值。"""

    value: Any = None

    @classmethod
    def success_value(cls, value: Any) -> "AskResult":
        return cls(
            state=ExecutionState.SUCCEEDED,
            display_text=json.dumps(value, ensure_ascii=False),
            output=json.dumps(value, ensure_ascii=False),
            value=value,
        )
