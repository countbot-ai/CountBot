"""Agent 工具调用的事件分发、通知与留痕。"""

import inspect
from typing import Any, Dict, List, Optional

from loguru import logger

from backend.modules.tools.outcome_projection import project_attempt


def append_tool_result(
    context_builder,
    messages: List[Dict[str, Any]],
    tool_call_id: str,
    tool_name: str,
    content: str,
) -> List[Dict[str, Any]]:
    """追加一条 tool 结果消息；有 context_builder 时走它的统一格式。"""
    if context_builder:
        return context_builder.add_tool_result(
            messages, tool_call_id, tool_name, content,
        )
    # 无 context_builder 时保持原地追加：调用方可能仍持有该列表的引用
    messages.append(
        {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": content,
        }
    )
    return messages


async def emit_tool_event(
    handler,
    event_type: str,
    payload: Dict[str, Any],
    *,
    failure_message: str = "Tool event handler failed",
) -> None:
    """调用 tool_event_handler（同步/异步均可），异常只记日志不影响主流程。"""
    if not handler:
        return
    try:
        maybe_result = handler(event_type, payload)
        if inspect.isawaitable(maybe_result):
            await maybe_result
    except Exception as e:
        logger.warning(f"{failure_message}: {e}")


async def notify_tool_phase(
    session_id: str,
    tool_name: str,
    arguments: Dict[str, Any],
    *,
    result: Optional[str] = None,
    error: Optional[str] = None,
    phase: Optional[str] = None,
) -> None:
    """向前端推送工具执行通知；失败只记日志。"""
    try:
        from backend.ws.tool_notifications import notify_tool_execution

        kwargs: Dict[str, Any] = {
            "session_id": session_id,
            "tool_name": tool_name,
            "arguments": arguments,
        }
        if result is not None:
            kwargs["result"] = result
        if error is not None:
            kwargs["error"] = error
        if phase is not None:
            kwargs["phase"] = phase
        await notify_tool_execution(**kwargs)
    except Exception as e:
        if error is not None:
            logger.warning(f"Failed to send tool error notification: {e}")
        elif result is not None:
            logger.warning(f"Failed to send tool result notification: {e}")
        else:
            logger.warning(f"Failed to send tool notification: {e}")


def record_tool_conversation(
    *,
    session_id: str,
    tool_name: str,
    arguments: Dict[str, Any],
    user_message: str,
    duration_ms: int,
    result: Optional[str] = None,
    error: Optional[str] = None,
    outcome=None,
    attempt_source: str = "agent_initial",
) -> None:
    """写入工具调用历史；outcome 存在时附带结构化执行投影。"""
    try:
        from backend.modules.tools.conversation_history import get_conversation_history

        get_conversation_history().add_conversation(
            session_id=session_id,
            tool_name=tool_name,
            arguments=arguments,
            user_message=user_message,
            result=result,
            error=error,
            duration_ms=duration_ms,
            outcome_projection=(
                project_attempt(outcome, source=attempt_source, session_id=session_id)
                if outcome is not None
                else None
            ),
        )
    except Exception as e:
        logger.warning(f"Failed to record tool conversation: {e}")
