"""MCP 工具包装器：把远端 tools / resources / prompts 适配成本地 Tool。"""

import asyncio
from typing import Any, Dict, List

from backend.modules.tools.base import Tool
from backend.modules.tools.execution import (
    ErrorCategory,
    RetrySafety,
    SideEffectState,
    ToolResult,
)

from backend.modules.mcp.helpers import (
    _execute_once,
    _normalize_schema_for_openai,
    _qualify_name,
    _remote_failure_result,
)


class _MCPWrapperBase(Tool):
    """MCP 包装器基类：统一 name/description/parameters 与文本接口。"""

    def _parameters_schema(self) -> Dict[str, Any]:
        raise NotImplementedError

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> Dict[str, Any]:
        return self._parameters_schema()


class MCPToolWrapper(_MCPWrapperBase):
    """包装单个远端 MCP tool。"""

    def __init__(self, session, server_name: str, tool_def, tool_timeout: int = 30):
        self._session = session
        self._original_name = tool_def.name
        self._name = _qualify_name(server_name, tool_def.name)
        self._description = tool_def.description or tool_def.name
        raw_schema = tool_def.inputSchema or {"type": "object", "properties": {}}
        self._parameters = _normalize_schema_for_openai(raw_schema)
        self._tool_timeout = tool_timeout

    def _parameters_schema(self) -> Dict[str, Any]:
        return self._parameters

    async def execute_outcome(self, **kwargs: Any) -> ToolResult:
        try:
            result = await _execute_once(
                lambda: self._session.call_tool(self._original_name, arguments=kwargs),
                self._tool_timeout,
            )
        except asyncio.CancelledError as exc:
            task = asyncio.current_task()
            if task is not None and task.cancelling() > 0:
                raise
            return _remote_failure_result(
                exc,
                label="MCP tool call",
                retry_safety=RetrySafety.UNKNOWN,
                side_effecting=True,
            )
        except Exception as exc:
            return _remote_failure_result(
                exc,
                label="MCP tool call",
                retry_safety=RetrySafety.UNKNOWN,
                side_effecting=True,
            )

        if result is None or not hasattr(result, "content"):
            return ToolResult.unknown_outcome(
                ErrorCategory.RESULT_CONTRACT,
                "(MCP tool returned a malformed result)",
                retry_safety=RetrySafety.UNKNOWN,
            )
        parts = self._content_parts(result.content)
        if bool(getattr(result, "isError", False)):
            return ToolResult.unknown_outcome(
                ErrorCategory.EXECUTION,
                "\n".join(parts) if parts else "(MCP tool reported an error)",
                retry_safety=RetrySafety.UNKNOWN,
            )
        if not parts:
            return ToolResult.unknown_outcome(
                ErrorCategory.RESULT_CONTRACT,
                "(MCP tool returned an empty result)",
                retry_safety=RetrySafety.UNKNOWN,
            )
        output = "\n".join(parts)
        return ToolResult.success(
            output,
            retry_safety=RetrySafety.UNKNOWN,
            side_effect_state=SideEffectState.COMMITTED,
        )

    @staticmethod
    def _content_parts(contents: Any) -> List[str]:
        if not isinstance(contents, (list, tuple)):
            return []
        parts: List[str] = []
        for content in contents:
            text = getattr(content, "text", None)
            parts.append(str(text) if text is not None else str(content))
        return parts



class MCPResourceWrapper(_MCPWrapperBase):
    """单个 MCP resource 的包装器；注册已改用聚合的 MCPResourceCatalogWrapper，本类用于按 URI 精确绑定。"""

    def __init__(self, session, server_name: str, resource_def, resource_timeout: int = 30):
        self._session = session
        self._name = _qualify_name(server_name, f"resource_{resource_def.name}")
        self._uri = str(resource_def.uri)
        desc = resource_def.description or resource_def.name
        self._description = f"[MCP Resource] {desc}\nURI: {self._uri}"
        self._resource_timeout = resource_timeout

    def _parameters_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute_outcome(self, **kwargs: Any) -> ToolResult:
        try:
            result = await _execute_once(
                lambda: self._session.read_resource(self._uri),
                self._resource_timeout,
            )
        except asyncio.CancelledError as exc:
            return _remote_failure_result(
                exc,
                label="MCP resource read",
                retry_safety=RetrySafety.SAFE,
                side_effecting=False,
            )
        except Exception as exc:
            return _remote_failure_result(
                exc,
                label="MCP resource read",
                retry_safety=RetrySafety.SAFE,
                side_effecting=False,
            )

        contents = getattr(result, "contents", None)
        if not isinstance(contents, (list, tuple)) or not contents:
            return ToolResult.failure(
                ErrorCategory.RESULT_CONTRACT,
                "(MCP resource returned an empty or malformed result)",
                retry_safety=RetrySafety.SAFE,
                side_effect_state=SideEffectState.NOT_APPLICABLE,
            )
        parts = [
            str(getattr(content, "text", None))
            if getattr(content, "text", None) is not None
            else str(content)
            for content in contents
        ]
        return ToolResult.success(
            "\n".join(parts),
            retry_safety=RetrySafety.SAFE,
            side_effect_state=SideEffectState.NOT_APPLICABLE,
        )



class MCPResourceCatalogWrapper(_MCPWrapperBase):
    """以单个工具暴露某 MCP 服务器的全部资源（工具面由 N 降为 1），模型通过 uri 参数选择目标。"""

    # 描述中列出的资源条目上限，避免描述本身过长
    MAX_LISTED_RESOURCES = 20

    def __init__(self, session, server_name: str, resources, resource_timeout: int = 30):
        self._session = session
        self._name = _qualify_name(server_name, "read_resource")
        self._resource_timeout = resource_timeout
        self._entries = [
            {
                "uri": str(getattr(resource, "uri", "")),
                "name": str(getattr(resource, "name", "") or getattr(resource, "uri", "")),
                "description": str(getattr(resource, "description", "") or ""),
            }
            for resource in resources
        ]

        lines = [f"[MCP Resources] server `{server_name}` exposes {len(self._entries)} resource(s):"]
        for entry in self._entries[: self.MAX_LISTED_RESOURCES]:
            suffix = f" — {entry['description']}" if entry["description"] else ""
            lines.append(f"- {entry['uri']}{suffix}")
        if len(self._entries) > self.MAX_LISTED_RESOURCES:
            remaining = len(self._entries) - self.MAX_LISTED_RESOURCES
            lines.append(f"- ... and {remaining} more")
        self._description = "\n".join(lines)

    def _parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "uri": {
                    "type": "string",
                    "description": "URI of the resource to read (see the resource list in the tool description).",
                }
            },
            "required": ["uri"],
        }

    async def execute_outcome(self, **kwargs: Any) -> ToolResult:
        uri = str(kwargs.get("uri") or "").strip()
        if not uri:
            return ToolResult.failure(
                ErrorCategory.VALIDATION,
                "Error: 'uri' is required. Use one of the URIs listed in the tool description.",
                retry_safety=RetrySafety.SAFE,
                side_effect_state=SideEffectState.NOT_APPLICABLE,
            )
        try:
            result = await _execute_once(
                lambda: self._session.read_resource(uri),
                self._resource_timeout,
            )
        except asyncio.CancelledError as exc:
            return _remote_failure_result(
                exc,
                label="MCP resource read",
                retry_safety=RetrySafety.SAFE,
                side_effecting=False,
            )
        except Exception as exc:
            return _remote_failure_result(
                exc,
                label="MCP resource read",
                retry_safety=RetrySafety.SAFE,
                side_effecting=False,
            )

        contents = getattr(result, "contents", None)
        if not isinstance(contents, (list, tuple)) or not contents:
            return ToolResult.failure(
                ErrorCategory.RESULT_CONTRACT,
                f"(MCP resource '{uri}' returned an empty or malformed result)",
                retry_safety=RetrySafety.SAFE,
                side_effect_state=SideEffectState.NOT_APPLICABLE,
            )
        parts = [
            str(getattr(content, "text", None))
            if getattr(content, "text", None) is not None
            else str(content)
            for content in contents
        ]
        return ToolResult.success(
            "\n".join(parts),
            retry_safety=RetrySafety.SAFE,
            side_effect_state=SideEffectState.NOT_APPLICABLE,
        )

class MCPPromptWrapper(_MCPWrapperBase):
    """包装远端 MCP prompt，把 prompt 参数映射成工具参数。"""

    def __init__(self, session, server_name: str, prompt_def, prompt_timeout: int = 30):
        self._session = session
        self._prompt_name = prompt_def.name
        self._name = _qualify_name(server_name, f"prompt_{prompt_def.name}")
        desc = prompt_def.description or prompt_def.name
        self._description = f"[MCP Prompt] {desc}"
        self._prompt_timeout = prompt_timeout
        properties: Dict[str, Any] = {}
        required: List[str] = []
        if prompt_def.arguments:
            for arg in prompt_def.arguments:
                prop: Dict[str, Any] = {"type": "string", "description": arg.description or arg.name}
                if arg.required:
                    required.append(arg.name)
                properties[arg.name] = prop
        self._parameters: Dict[str, Any] = {
            "type": "object",
            "properties": properties,
            "required": required,
        }

    def _parameters_schema(self) -> Dict[str, Any]:
        return self._parameters

    async def execute_outcome(self, **kwargs: Any) -> ToolResult:
        try:
            result = await _execute_once(
                lambda: self._session.get_prompt(
                    self._prompt_name,
                    arguments=kwargs,
                ),
                self._prompt_timeout,
            )
        except asyncio.CancelledError as exc:
            return _remote_failure_result(
                exc,
                label="MCP prompt",
                retry_safety=RetrySafety.SAFE,
                side_effecting=False,
            )
        except Exception as exc:
            return _remote_failure_result(
                exc,
                label="MCP prompt",
                retry_safety=RetrySafety.SAFE,
                side_effecting=False,
            )

        messages = getattr(result, "messages", None)
        if not isinstance(messages, (list, tuple)) or not messages:
            return ToolResult.failure(
                ErrorCategory.RESULT_CONTRACT,
                "(MCP prompt returned an empty or malformed result)",
                retry_safety=RetrySafety.SAFE,
                side_effect_state=SideEffectState.NOT_APPLICABLE,
            )
        parts: List[str] = []
        for message in messages:
            content = getattr(message, "content", None)
            text = getattr(content, "text", None)
            parts.append(str(text) if text is not None else str(message))
        output = "\n".join(parts)
        return ToolResult.success(
            output,
            retry_safety=RetrySafety.SAFE,
            side_effect_state=SideEffectState.NOT_APPLICABLE,
        )
