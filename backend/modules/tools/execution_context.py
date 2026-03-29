"""Shared runtime context for tool executions."""

from __future__ import annotations

import contextvars
import inspect
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from loguru import logger


ToolEventHandler = Callable[[str, Dict[str, Any]], Any]


@dataclass(slots=True)
class ToolExecutionContext:
    """Runtime metadata for the current tool call."""

    session_id: Optional[str]
    tool_name: str
    event_handler: Optional[ToolEventHandler] = None


_tool_execution_context: contextvars.ContextVar[Optional[ToolExecutionContext]] = (
    contextvars.ContextVar("tool_execution_context", default=None)
)


def push_tool_execution_context(
    context: ToolExecutionContext,
) -> contextvars.Token[Optional[ToolExecutionContext]]:
    """Push the current tool execution context."""

    return _tool_execution_context.set(context)


def reset_tool_execution_context(
    token: contextvars.Token[Optional[ToolExecutionContext]],
) -> None:
    """Restore the previous tool execution context."""

    _tool_execution_context.reset(token)


def get_current_tool_execution_context() -> Optional[ToolExecutionContext]:
    """Return the current tool execution context, if any."""

    return _tool_execution_context.get()


async def emit_tool_progress(
    progress: int,
    message: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """Emit a progress update for the current tool execution."""

    context = get_current_tool_execution_context()
    if context is None:
        return

    normalized_progress = max(0, min(100, int(progress)))
    details_payload = dict(details or {})
    payload: Dict[str, Any] = {
        "tool_name": context.tool_name,
        "progress": normalized_progress,
        "message": message,
        "session_id": context.session_id,
        "details": details_payload or None,
    }
    if details_payload:
        payload.update(details_payload)

    if context.session_id:
        try:
            from backend.ws.tool_notifications import notify_tool_progress

            await notify_tool_progress(
                session_id=context.session_id,
                tool_name=context.tool_name,
                progress=normalized_progress,
                message=message,
                details=details_payload or None,
            )
        except Exception as exc:
            logger.warning(f"Failed to emit WebSocket tool progress: {exc}")

    if context.event_handler:
        try:
            maybe_result = context.event_handler("tool_progress", payload)
            if inspect.isawaitable(maybe_result):
                await maybe_result
        except Exception as exc:
            logger.warning(f"Failed to emit tool progress event: {exc}")
