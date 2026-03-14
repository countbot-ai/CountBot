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
        return (
            "【必须使用】将用户消息转发给AI处理。"
            "规则：不询问、不闲聊、收到内容立即调用此工具、等待返回结果再回复。"
            "调用格式：send_message({\"text\": \"用户说的话\"})"
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "用户的消息内容，直接传递用户说的话，不要修改。"
                },
                "message": {
                    "type": "string",
                    "description": "用户的消息内容（与text作用相同，二选一）。"
                }
            },
            "required": ["text"],
            "additionalProperties": False
        }

    async def execute(self, message: str = "", **kwargs) -> Any:
        # 实际响应由 XiaozhiChannel._handle_tool_call 通过 Future 机制处理
        return {"status": "received", "user_message": message}

