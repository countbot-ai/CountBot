"""示例工具实现

演示如何通过继承 Tool 基类来实现具体工具。
"""

from typing import Any

from backend.modules.tools.base import Tool


class EchoTool(Tool):
    """回显工具 - 回显输入消息，用于测试工具执行"""

    @property
    def name(self) -> str:
        return "echo"

    @property
    def description(self) -> str:
        return "Echoes back the input message. Useful for testing tool execution."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The message to echo back",
                },
                "uppercase": {
                    "type": "boolean",
                    "description": "Whether to convert the message to uppercase",
                    "default": False,
                },
            },
            "required": ["message"],
        }

    async def execute(self, **kwargs: Any) -> str:
        """
        执行回显操作
        
        Args:
            message: 要回显的消息
            uppercase: 是否转换为大写
            
        Returns:
            str: 回显的消息
        """
        message = kwargs.get("message", "")
        uppercase = kwargs.get("uppercase", False)
        
        result = message.upper() if uppercase else message
        return f"Echo: {result}"
