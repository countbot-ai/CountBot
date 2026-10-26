"""MCP 客户端门面：重新导出 helpers/wrappers/connection/manager 的对外符号，保持既有导入路径不变。"""

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
