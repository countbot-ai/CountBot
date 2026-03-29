"""小智AI send_message 工具

仅在小智频道启用且 enable_conversation=True 时注册。
小智AI通过此工具将用户语音转发给 Agent 处理。
"""

from typing import Any, Dict

from backend.modules.tools.base import Tool


class XiaozhiMessageTool(Tool):
    """小智AI消息工具 - 接收用户语音消息并转发给 Agent 处理"""

    @property
    def name(self) -> str:
        return "send_message"

    @property
    def description(self) -> str:
        return "Forward the raw user message to the agent immediately."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Raw user message."
                },
                "message": {
                    "type": "string",
                    "description": "Alias of `text`."
                }
            },
            "required": ["text"],
            "additionalProperties": False
        }

    async def execute(self, message: str = "", **kwargs) -> Any:
        # 实际响应由 XiaozhiChannel._handle_tool_call 通过 Future 机制处理
        return {"status": "received", "user_message": message}
