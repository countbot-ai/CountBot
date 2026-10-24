"""MCP 客户端模块

原单文件实现已按职责拆分：

- ``helpers``    —— 常量、名称构造、schema 归一、失败结果构造
- ``wrappers``   —— 远端 tools / resources / prompts 的 Tool 适配器
- ``connection`` —— 服务器连接与连通性测试
- ``manager``    —— 客户端管理器（生命周期、注册、健康检查）

本模块作为门面重新导出全部对外符号，保持既有导入路径不变。
"""

from backend.modules.mcp.connection import (
    connect_mcp_server,
    test_mcp_server,
)
from backend.modules.mcp.helpers import (
    _execute_once,
    _infer_transport,
    _is_transient,
    _mcp_error_text,
    _normalize_schema_for_openai,
    _normalize_windows_stdio_command,
    _qualify_name,
    _remote_failure_result,
)
from backend.modules.mcp.manager import McpClientManager
from backend.modules.mcp.wrappers import (
    MCPPromptWrapper,
    MCPResourceCatalogWrapper,
    MCPResourceWrapper,
    MCPToolWrapper,
)

__all__ = [
    "McpClientManager",
    "MCPToolWrapper",
    "MCPResourceWrapper",
    "MCPResourceCatalogWrapper",
    "MCPPromptWrapper",
    "connect_mcp_server",
    "test_mcp_server",
]
