"""MCP 客户端的内部辅助函数与常量。"""

import asyncio
import os
import re
import shutil
from typing import Dict, List

from backend.modules.config.schema import McpServerConfig
from backend.modules.tools.execution import (
    ErrorCategory,
    ExecutionState,
    RetrySafety,
    SideEffectState,
    ToolResult,
)

_TRANSIENT_EXC_NAMES: frozenset[str] = frozenset((
    "ClosedResourceError",
    "BrokenResourceError",
    "EndOfStream",
    "BrokenPipeError",
    "ConnectionResetError",
    "ConnectionRefusedError",
    "ConnectionAbortedError",
    "ConnectionError",
))

_WINDOWS_SHELL_LAUNCHERS: frozenset[str] = frozenset((
    "npx", "npm", "pnpm", "yarn", "bunx",
))

_SANITIZE_RE = re.compile(r"_+")


def _qualify_name(server_name: str, local_name: str) -> str:
    """构造 MCP 工具名：``mcp__server__tool``。

    双下划线作分隔符，使 server 与 tool 中的单下划线不会造成歧义——
    用单下划线拼接时 ``mcp_a_b`` 无法判断是「server=a, tool=b」还是
    「server=a_b」。两侧各自只压掉多余下划线，不合并分隔符。
    """
    server_part = _SANITIZE_RE.sub("_", re.sub(r"[^a-zA-Z0-9_-]", "_", server_name)).strip("_")
    tool_part = _SANITIZE_RE.sub("_", re.sub(r"[^a-zA-Z0-9_-]", "_", local_name)).strip("_")
    return f"mcp__{server_part}__{tool_part}"


def _is_transient(exc: BaseException) -> bool:
    return type(exc).__name__ in _TRANSIENT_EXC_NAMES


def _normalize_windows_stdio_command(
    command: str,
    args: List[str],
    env: Dict[str, str],
) -> tuple[str, List[str], Dict[str, str]]:
    if os.name != "nt":
        return command, args, env
    base = command.lower().strip()
    if base.endswith(".exe") or base.endswith(".com"):
        return command, args, env
    if base in ("cmd", "cmd.exe", "powershell", "pwsh"):
        return command, args, env
    resolved = shutil.which(command)
    if resolved:
        resolved_lower = resolved.lower()
        if resolved_lower.endswith(".exe") or resolved_lower.endswith(".com"):
            return command, args, env
        if resolved_lower.endswith(".cmd") or resolved_lower.endswith(".bat"):
            pass
        elif base not in _WINDOWS_SHELL_LAUNCHERS:
            return command, args, env
    elif base not in _WINDOWS_SHELL_LAUNCHERS:
        return command, args, env
    comspec = env.get("COMSPEC") or os.environ.get("COMSPEC", "cmd.exe")
    new_args = ["/d", "/c", command] + list(args)
    return comspec, new_args, env


def _infer_transport(config: McpServerConfig) -> str:
    if config.transport:
        return config.transport
    if config.command:
        return "stdio"
    if config.url:
        return "sse" if config.url.rstrip("/").endswith("/sse") else "streamable_http"
    return ""


def _normalize_schema_for_openai(schema: dict) -> dict:
    if not isinstance(schema, dict):
        return {"type": "object", "properties": {}}
    if schema.get("type") in (["string", "null"], ["null", "string"]):
        schema = {**schema, "type": "string", "nullable": True}
    if "anyOf" in schema:
        non_null = [s for s in schema["anyOf"] if s.get("type") != "null"]
        if len(non_null) == 1:
            merged = {**non_null[0], "nullable": True}
            for k in ("title", "description", "default"):
                if k in schema and k not in merged:
                    merged[k] = schema[k]
            schema = merged
        else:
            schema = {**schema}
            del schema["anyOf"]
    for key in ("properties", "items"):
        child = schema.get(key)
        if isinstance(child, dict):
            schema = {**schema, key: _normalize_schema_for_openai(child)}
    if "required" in schema and not isinstance(schema["required"], list):
        schema = {**schema, "required": list(schema["required"])}
    return schema


def _mcp_error_text(exc: BaseException, label: str) -> str:
    """Render an MCP exception without using the text as outcome authority."""

    if type(exc).__name__ == "McpError":
        err = getattr(exc, "error", None)
        code = getattr(err, "code", "?") if err else "?"
        message = getattr(err, "message", str(exc)) if err else str(exc)
        return f"({label} failed: MCP error {code}: {message})"
    return f"({label} failed: {type(exc).__name__}: {exc})"


async def _execute_once(coro_factory, timeout: int):
    """Perform exactly one MCP SDK operation invocation.

    A second call to ``coro_factory`` is a new physical execution and must enter
    the registry's canonical attempt boundary instead of being hidden here.
    """

    return await asyncio.wait_for(coro_factory(), timeout=timeout)


def _remote_failure_result(
    exc: BaseException,
    *,
    label: str,
    retry_safety: RetrySafety,
    side_effecting: bool,
) -> ToolResult:
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        category = ErrorCategory.TIMEOUT
        retryable = True
        display = f"({label} timed out)"
    elif isinstance(exc, asyncio.CancelledError):
        category = ErrorCategory.CANCELLATION
        retryable = False
        display = f"({label} was cancelled)"
    else:
        category = ErrorCategory.DEPENDENCY
        retryable = _is_transient(exc)
        display = _mcp_error_text(exc, label)

    if side_effecting:
        return ToolResult.unknown_outcome(
            category,
            display,
            retryable=retryable,
            retry_safety=retry_safety,
        )
    if category is ErrorCategory.CANCELLATION:
        return ToolResult(
            state=ExecutionState.CANCELLED,
            display_text=display,
            error_category=category,
            retry_safety=retry_safety,
            side_effect_state=SideEffectState.NOT_APPLICABLE,
        )
    return ToolResult.failure(
        category,
        display,
        retryable=retryable,
        retry_safety=retry_safety,
        side_effect_state=SideEffectState.NOT_APPLICABLE,
    )
