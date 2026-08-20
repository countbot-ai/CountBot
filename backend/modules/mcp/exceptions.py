"""MCP Exceptions - MCP异常定义

统一的MCP异常体系，便于错误处理和日志记录。
"""


class McpError(Exception):
    """MCP异常基类"""

    def __init__(self, message: str, details: dict = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self):
        """转换为字典格式"""
        return {
            "error": self.__class__.__name__,
            "message": self.message,
            "details": self.details,
        }


class McpConnectionError(McpError):
    """MCP连接错误"""
    pass


class McpTimeoutError(McpConnectionError):
    """MCP超时错误"""
    pass


class McpValidationError(McpError):
    """MCP配置验证错误"""
    pass


class McpServerNotFoundError(McpError):
    """MCP服务器未找到"""
    pass


class McpToolExecutionError(McpError):
    """MCP工具执行错误"""
    pass


class McpRegistryError(McpError):
    """MCP注册表错误"""
    pass


class McpImportError(McpError):
    """MCP包导入错误"""
    pass
