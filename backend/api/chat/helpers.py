"""
Chat API 的辅助函数。

参数归一化、消息上下文提取、工具调用结果整形。不依赖请求上下文，
各路由模块共用。
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

from fastapi import HTTPException, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.agent.loop import AgentLoop
from backend.modules.agent.team_commands import resolve_explicit_team_command
from backend.modules.config.loader import config_loader
from backend.modules.external_agents.conversation import (
    build_history_prompt,
    resolve_effective_session_mode,
)
from backend.modules.external_agents.routing import (
    build_explicit_external_agent_system_message,
    extract_explicit_external_agent_request,
)
from backend.modules.config.schema import ModelConfig, PersonaConfig
from backend.modules.tools.execution import ExecutionState, ToolExecutionInProgress, ToolExecutionRejected
from backend.modules.session.message_context import (
    MAX_CHAT_ATTACHMENTS,
    extract_attachment_items_from_message_context,
    extract_reasoning_content_from_message_context,
    resolve_workspace_attachments,
)
from backend.utils.datetime_utils import to_utc_iso
from backend.utils.paths import WORKSPACE_DIR

from backend.api.chat.models import ToolCallResponse

MAX_CHAT_ATTACHMENT_SIZE = 25 * 1024 * 1024
DEFAULT_TOOL_PREVIEW_LIMIT = 1200
MAX_TOOL_PREVIEW_LIMIT = 8000
SPECIAL_HISTORY_TOOL_NAMES = {"spawn", "workflow_run"}


def _normalize_api_mode(value: Any) -> str:
    return "chat_completions"


def _extract_reasoning_content_from_message_context(raw: Optional[str]) -> Optional[str]:
    return extract_reasoning_content_from_message_context(raw)


def _extract_attachment_items_from_message_context(raw: Optional[str]) -> List[Dict[str, Any]]:
    return extract_attachment_items_from_message_context(raw)


def _resolve_active_workspace() -> Path:
    config = config_loader.config
    return Path(config.workspace.path) if config.workspace.path else WORKSPACE_DIR


def _normalize_session_model_overrides(raw_model: Dict[str, Any]) -> Dict[str, Any]:
    """校验并标准化会话级模型覆盖配置。"""
    config = config_loader.config
    candidate = dict(raw_model)
    api_key = candidate.pop("api_key", None)
    api_base = candidate.pop("api_base", None)

    if "api_mode" in candidate:
        candidate["api_mode"] = _normalize_api_mode(candidate.get("api_mode"))

    effective_model_data = config.model.model_dump()
    for key, value in candidate.items():
        if value is not None:
            effective_model_data[key] = value

    validated_model = ModelConfig(**effective_model_data)
    validated_dump = validated_model.model_dump()

    normalized_overrides: Dict[str, Any] = {}
    for key in candidate:
        normalized_overrides[key] = validated_dump[key]

    if "api_key" in raw_model:
        normalized_overrides["api_key"] = "" if api_key is None else str(api_key)
    if "api_base" in raw_model:
        normalized_overrides["api_base"] = "" if api_base is None else str(api_base).strip()

    return normalized_overrides


def _normalize_session_persona_overrides(raw_persona: Dict[str, Any]) -> Dict[str, Any]:
    """校验并标准化会话级 persona 覆盖配置。"""
    config = config_loader.config
    candidate = dict(raw_persona)

    if "heartbeat" in candidate and candidate["heartbeat"] is not None:
        heartbeat_override = candidate["heartbeat"]
        if not isinstance(heartbeat_override, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="persona_config.heartbeat must be an object",
            )

        base_heartbeat = config.persona.heartbeat.model_dump()
        candidate["heartbeat"] = {
            **base_heartbeat,
            **{key: value for key, value in heartbeat_override.items() if value is not None},
        }

    effective_persona_data = config.persona.model_dump()
    for key, value in candidate.items():
        if value is not None:
            effective_persona_data[key] = value

    validated_persona = PersonaConfig(**effective_persona_data)
    validated_dump = validated_persona.model_dump()

    return {
        key: validated_dump[key]
        for key in candidate
    }


async def _require_session(db: AsyncSession, session_id: str):
    from sqlalchemy import select
    from backend.models.session import Session

    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found"
        )
    return session


def _validate_message_or_attachments(message: str, attachments: Optional[List[str]]) -> str:
    normalized_message = str(message or "")
    if normalized_message.strip() or attachments:
        return normalized_message
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Message or attachments are required"
    )


def _resolve_attachment_inputs(attachments: Optional[List[str]], workspace: Path) -> List[tuple[str, Path]]:
    try:
        return resolve_workspace_attachments(attachments, workspace=workspace, max_attachments=MAX_CHAT_ATTACHMENTS)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


async def _notify_webui_session_updated(session_id: str) -> None:
    """通知 WebUI 指定会话和会话列表需要刷新。"""
    try:
        from backend.ws.connection import (
            ServerMessage,
            connection_manager,
            send_dict_to_session,
        )

        await send_dict_to_session(
            session_id,
            {
                "type": "history_updated",
                "sessionId": session_id,
            },
        )
        await connection_manager.broadcast(ServerMessage(type="sessions_updated"))
    except Exception as exc:
        logger.debug(f"Failed to notify WebUI for session {session_id}: {exc}")

def _clamp_tool_preview_limit(value: int) -> int:
    return max(120, min(int(value), MAX_TOOL_PREVIEW_LIMIT))


def _parse_tool_arguments(raw: Optional[str]) -> Dict[str, Any]:
    if not raw:
        return {}

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}

    if isinstance(parsed, dict):
        return parsed
    return {"value": parsed}


def _truncate_text(value: Optional[str], limit: int) -> tuple[Optional[str], bool]:
    if value is None:
        return None, False

    normalized = str(value)
    if len(normalized) <= limit:
        return normalized, False

    trimmed = normalized[:limit].rstrip()
    return f"{trimmed}\n...", True


def _extract_spawn_task_id(result_text: Optional[str]) -> Optional[str]:
    if not result_text:
        return None

    try:
        parsed = json.loads(result_text)
        if isinstance(parsed, dict) and parsed.get("task_id"):
            return str(parsed["task_id"]).strip()
    except (TypeError, json.JSONDecodeError):
        pass

    match = re.search(r"\(ID: ([a-f0-9\-]+)\)", result_text)
    if match:
        return match.group(1)
    return None


async def _load_spawn_task_detail(
    *,
    tool_call_result: Optional[str],
    subagent_mgr,
    db: AsyncSession,
) -> Optional[Dict[str, Any]]:
    task_id = _extract_spawn_task_id(tool_call_result)
    if not task_id:
        return None

    if subagent_mgr:
        task = subagent_mgr.get_task(task_id)
        if task:
            return task.to_dict()

    from sqlalchemy import select
    from backend.models.task import Task as TaskModel

    result = await db.execute(
        select(TaskModel).where(TaskModel.id == task_id)
    )
    db_task = result.scalar_one_or_none()
    if not db_task:
        return None

    tool_call_records = []
    if db_task.tool_call_records:
        try:
            tool_call_records = json.loads(db_task.tool_call_records)
        except json.JSONDecodeError as exc:
            logger.warning(f"Failed to parse tool_call_records: {exc}")

    from backend.modules.tools.outcome_projection import task_read_view
    task_status, projection_state, projection = task_read_view(
        db_task.status, db_task.outcome_projection,
    )
    return {
        "task_id": db_task.id,
        "label": db_task.label,
        "message": db_task.message,
        "session_id": db_task.session_id,
        "status": task_status,
        "progress": db_task.progress,
        "result": db_task.result,
        "error": db_task.error,
        "created_at": to_utc_iso(db_task.created_at),
        "started_at": to_utc_iso(db_task.started_at),
        "completed_at": to_utc_iso(db_task.completed_at),
        "tool_call_records": tool_call_records,
        "outcome_projection": projection,
        "outcome_projection_state": projection_state,
    }


async def _build_tool_call_response(
    *,
    tc,
    db: AsyncSession,
    subagent_mgr,
    tool_mode: Literal["full", "summary", "none"] = "full",
    preview_limit: int = DEFAULT_TOOL_PREVIEW_LIMIT,
) -> ToolCallResponse:
    arguments = _parse_tool_arguments(tc.arguments)

    # 新历史优先读结构化 state；旧行继续按原 error 文本呈现。
    from backend.modules.tools.outcome_projection import (
        ProjectionState, projection_state, read_stored_projection,
    )
    stored_projection = getattr(tc, "outcome_projection", None)
    projection = read_stored_projection(stored_projection)
    state = projection_state(stored_projection)
    status_value = (
        "success" if projection["state"] == "SUCCEEDED" else "error"
    ) if state is ProjectionState.RECOGNIZED else (
        "error" if tc.error else "success"
    ) if state is ProjectionState.ABSENT else "unknown"
    use_full_payload = tool_mode == "full" or tc.tool_name in SPECIAL_HISTORY_TOOL_NAMES

    result_text = tc.result
    error_text = tc.error
    result_truncated = False
    error_truncated = False
    detail_available = False
    detail_loaded = True

    if tool_mode == "summary" and not use_full_payload:
        result_text, result_truncated = _truncate_text(tc.result, preview_limit)
        error_text, error_truncated = _truncate_text(tc.error, preview_limit)
        detail_available = result_truncated or error_truncated
        detail_loaded = not detail_available

    spawn_task = None
    if tc.tool_name == "spawn":
        spawn_task = await _load_spawn_task_detail(
            tool_call_result=tc.result,
            subagent_mgr=subagent_mgr,
            db=db,
        )

    return ToolCallResponse(
        id=tc.id,
        name=tc.tool_name,
        arguments=arguments,
        result=result_text,
        error=error_text,
        status=status_value,
        duration=tc.duration_ms,
        spawn_task=spawn_task,
        detail_available=detail_available,
        detail_loaded=detail_loaded,
        result_truncated=result_truncated,
        error_truncated=error_truncated,
    )


def _resolve_explicit_external_tool_request(
    agent_loop: AgentLoop,
    message: str,
) -> Optional[tuple[str, str]]:
    """Resolve natural-language routing like '用 claude 帮我写个爬虫'."""
    parsed = extract_explicit_external_agent_request(message)
    if not parsed or not agent_loop.tools:
        return None

    requested_profile, task = parsed
    external_tool = agent_loop.tools.get_tool("external_coding_agent")
    registry = getattr(external_tool, "registry", None)
    if registry is None:
        return None

    try:
        canonical_name = registry.resolve_profile_name(requested_profile)
        registry.resolve_profile(canonical_name)
    except Exception:
        return None

    return canonical_name, task


def _resolve_explicit_team_workflow_request(
    agent_loop: AgentLoop,
    message: str,
) -> Optional[tuple[str, str]]:
    """Resolve explicit deterministic workflow command: /team <team_name> <goal>."""
    context_builder = getattr(agent_loop, "context_builder", None)
    return resolve_explicit_team_command(
        context_builder,
        message,
        log_scope="web chat explicit team command",
    )


def _prepare_external_task(profile, task: str, history: list[dict]) -> str:
    """根据 profile 会话模式构造实际任务。"""
    session_mode = resolve_effective_session_mode(profile)
    if session_mode in {"stateless", "native"}:
        return task
    return build_history_prompt(
        task=task,
        history_messages=history,
        history_message_count=profile.history_message_count,
    )


def _inject_explicit_external_request_context(
    agent_loop: AgentLoop,
    context: list[dict],
    explicit_external_request: Optional[tuple[str, str]],
) -> list[dict]:
    """Force WebUI explicit external-agent requests through the normal tool-call loop."""
    if not explicit_external_request:
        return list(context)

    external_tool = agent_loop.tools.get_tool("external_coding_agent") if agent_loop.tools else None
    registry = getattr(external_tool, "registry", None)
    if registry is None:
        return list(context)

    profile_name, task = explicit_external_request
    profile = registry.resolve_profile(profile_name)
    prepared_task = _prepare_external_task(profile, task, context)
    system_message = build_explicit_external_agent_system_message(
        profile.name,
        prepared_task,
    )
    if not system_message:
        return list(context)

    augmented_context = list(context)
    if augmented_context and augmented_context[0].get("role") == "system":
        existing_content = str(augmented_context[0].get("content", "") or "")
        separator = "\n\n" if existing_content else ""
        augmented_context[0] = {
            **augmented_context[0],
            "content": f"{existing_content}{separator}{system_message}",
        }
    else:
        augmented_context.insert(0, {"role": "system", "content": system_message})
    return augmented_context
