"""Chat API 端点"""

import asyncio
import json
import re
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import unquote
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db, get_db_session_factory
from backend.modules.agent.context import ContextBuilder
from backend.modules.agent.loop import AgentLoop
from backend.modules.agent.memory import MemoryStore
from backend.modules.agent.skills import SkillsLoader
from backend.modules.agent.team_commands import (
    build_team_command_overview,
    build_team_goal_usage,
    resolve_explicit_team_command,
)
from backend.modules.config.loader import config_loader
from backend.modules.config.schema import ModelConfig, PersonaConfig
from backend.modules.external_agents.conversation import (
    build_history_prompt,
    resolve_effective_session_mode,
)
from backend.modules.external_agents.routing import (
    build_explicit_external_agent_system_message,
    extract_explicit_external_agent_request,
)
from backend.modules.providers import create_provider
from backend.modules.providers.runtime import (
    build_provider_unavailable_message,
    get_provider_runtime_state,
)
from backend.modules.session import (
    ConversationContextService,
    resolve_session_runtime_config,
    schedule_context_maintenance,
)
from backend.modules.session.manager import SessionManager
from backend.modules.session.message_context import (
    MAX_CHAT_ATTACHMENTS,
    build_attachment_item,
    build_attachment_items_from_workspace,
    build_message_context,
    build_workspace_attachment_destination,
    extract_attachment_items_from_message_context,
    extract_reasoning_content_from_message_context,
    normalize_assistant_persistence_payload,
    resolve_workspace_attachments,
)
from backend.modules.tools.registry import ToolRegistry
from backend.utils.datetime_utils import to_utc_iso
from backend.utils.paths import WORKSPACE_DIR

router = APIRouter(prefix="/api/chat", tags=["chat"])

MAX_CHAT_ATTACHMENT_SIZE = 25 * 1024 * 1024


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


# ============================================================================
# Request/Response Models
# ============================================================================


class SendMessageRequest(BaseModel):
    """发送消息请求"""

    session_id: str = Field(..., description="会话 ID")
    message: str = Field(default="", description="用户消息内容")
    attachments: Optional[List[str]] = Field(None, description="附件路径列表（可选）")


class AttachmentItemResponse(BaseModel):
    """附件响应"""

    path: str
    name: str
    size: int
    content_type: Optional[str] = None
    kind: str


class UpdateSessionSummaryRequest(BaseModel):
    """更新会话总结请求"""
    
    summary: str = Field(..., min_length=10, max_length=200, description="会话总结（10-200字符）")


class SummarizeSessionResponse(BaseModel):
    """总结会话响应"""
    
    success: bool = Field(..., description="是否成功")
    summary: str = Field(..., description="生成的总结")
    message: Optional[str] = Field(None, description="消息")


class SendMessageResponse(BaseModel):
    """发送消息响应"""

    message_id: str = Field(..., description="消息 ID")
    streaming: bool = Field(True, description="是否为流式响应")


class SessionResponse(BaseModel):
    """会话响应"""

    id: str
    name: str
    created_at: str
    updated_at: str
    summary: Optional[str] = None
    summary_updated_at: Optional[str] = None


class ToolCallResponse(BaseModel):
    """工具调用响应"""
    
    id: str
    name: str
    arguments: Dict[str, Any]
    result: Optional[str] = None
    error: Optional[str] = None
    status: str = "success"
    duration: Optional[int] = None
    spawn_task: Optional[Dict[str, Any]] = None  # 子代理任务详情（仅 spawn 工具调用）


class MessageResponse(BaseModel):
    """消息响应"""

    id: int
    session_id: str
    role: str
    content: str
    reasoning_content: Optional[str] = None
    attachment_items: List[AttachmentItemResponse] = Field(default_factory=list)
    created_at: str
    tool_calls: List[ToolCallResponse] = Field(default_factory=list, description="工具调用记录")


# ============================================================================
# Dependency Injection
# ============================================================================


# ============================================================================
# Global SubagentManager (shared across all requests)
# ============================================================================

_global_subagent_manager = None


def set_global_subagent_manager(manager):
    """设置全局 SubagentManager 实例"""
    global _global_subagent_manager
    _global_subagent_manager = manager
    logger.info("Global SubagentManager set")


def get_global_subagent_manager():
    """获取全局 SubagentManager 实例"""
    return _global_subagent_manager


async def get_agent_loop(
    request: Request,
    db: AsyncSession = Depends(get_db),
    session_id: Optional[str] = None
) -> AgentLoop:
    """获取 AgentLoop 实例（依赖注入）
    
    Args:
        request: FastAPI 请求对象
        db: 数据库会话
        session_id: 可选的会话 ID，如果提供则使用会话级配置
    """
    global _global_subagent_manager
    
    try:
        config = config_loader.config
        session = None

        if session_id:
            from sqlalchemy import select
            from backend.models.session import Session
            
            result = await db.execute(
                select(Session).where(Session.id == session_id)
            )
            session = result.scalar_one_or_none()

        runtime_config = resolve_session_runtime_config(config, session)
        if session_id and runtime_config.use_custom_config:
            logger.info(f"会话使用自定义运行时配置：{session_id}")
        
        from pathlib import Path
        workspace = Path(config.workspace.path) if config.workspace.path else WORKSPACE_DIR
        workspace.mkdir(parents=True, exist_ok=True)
        
        # 初始化 LLM Provider（使用有效配置）
        provider_name = runtime_config.provider_name
        runtime_state = get_provider_runtime_state(
            config,
            provider_name,
            api_key_override=runtime_config.api_key,
            api_base_override=runtime_config.api_base,
        )

        if not runtime_state.selectable:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=build_provider_unavailable_message(provider_name, runtime_state.reason)
            )
        
        provider = create_provider(
            api_key=runtime_state.api_key or None,
            api_base=runtime_state.api_base,
            default_model=runtime_config.model_name,
            api_mode=runtime_config.api_mode,
            timeout=120.0,
            max_retries=3,
            provider_id=provider_name,
        )
        
        # 初始化记忆系统和技能加载器
        memory_dir = workspace / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)
        memory = MemoryStore(memory_dir)
        
        # 优先使用全局 skills 实例（性能优化）
        shared = getattr(request.app.state, 'shared', None)
        if hasattr(request.app.state, 'skills'):
            skills = request.app.state.skills
            logger.debug("Using global skills instance from app.state")
        elif shared and shared.get('skills') is not None:
            skills = shared['skills']
            logger.debug("Using global skills instance from app.state")
        else:
            # 回退：创建临时实例
            skills_dir = workspace / "skills"
            skills_dir.mkdir(parents=True, exist_ok=True)
            skills = SkillsLoader(skills_dir)
            logger.warning("Creating temporary SkillsLoader instance in chat endpoint")
        
        context_builder = ContextBuilder(
            workspace=workspace,
            memory=memory,
            skills=skills,
            persona_config=runtime_config.persona_config,
        )
        
        # 创建或获取全局 SubagentManager
        from backend.modules.agent.subagent import SubagentManager
        
        if _global_subagent_manager is None:
            _global_subagent_manager = SubagentManager(
                provider=provider,
                workspace=workspace,
                model=config.model.model,
                temperature=config.model.temperature,
                max_tokens=config.model.max_tokens,
                db_session_factory=get_db_session_factory(),
                config_loader=config_loader,
                skills=skills,
            )
            logger.info("Created global SubagentManager")
        
        from backend.modules.tools.setup import register_all_tools
        
        tools = register_all_tools(
            workspace=workspace,
            command_timeout=config.security.command_timeout,
            max_output_length=config.security.max_output_length,
            allow_dangerous=not config.security.dangerous_commands_blocked,
            restrict_to_workspace=config.security.restrict_to_workspace,
            custom_deny_patterns=config.security.custom_deny_patterns,
            custom_allow_patterns=config.security.custom_allow_patterns if config.security.command_whitelist_enabled else None,
            audit_log_enabled=config.security.audit_log_enabled,
            subagent_manager=_global_subagent_manager,
            skills_loader=skills,
            session_id=None,
            memory_store=memory,
        )
        
        agent_loop = AgentLoop(
            provider=provider,
            workspace=workspace,
            tools=tools,
            context_builder=context_builder,
            subagent_manager=_global_subagent_manager,
            model=runtime_config.model_name,
            max_iterations=runtime_config.max_iterations,
            max_retries=3,
            retry_delay=1.0,
            temperature=runtime_config.temperature,
            max_tokens=runtime_config.max_tokens,
            thinking_enabled=runtime_config.thinking_enabled,
        )
        
        return agent_loop
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to initialize AgentLoop: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialize agent: {str(e)}"
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
    augmented_context.append({"role": "system", "content": system_message})
    return augmented_context


# ============================================================================
# Chat Endpoints
# ============================================================================


@router.post("/sessions/{session_id}/attachments", response_model=AttachmentItemResponse)
async def upload_chat_attachment(
    session_id: str,
    req: Request,
    db: AsyncSession = Depends(get_db),
) -> AttachmentItemResponse:
    """将前端拖拽/粘贴/选择的文件写入当前工作空间附件目录。"""
    await _require_session(db, session_id)

    raw_filename = req.headers.get("x-file-name", "").strip()
    try:
        decoded_filename = Path(unquote(raw_filename)).name if raw_filename else ""
    except Exception:
        decoded_filename = raw_filename or ""

    content_type = req.headers.get("content-type", "").strip() or None
    declared_size = req.headers.get("x-file-size", "").strip()
    if declared_size:
        try:
            declared_size_int = int(declared_size)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid X-File-Size header",
            ) from exc
        if declared_size_int < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid X-File-Size header",
            )
        if declared_size_int > MAX_CHAT_ATTACHMENT_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Attachment exceeds max size {MAX_CHAT_ATTACHMENT_SIZE} bytes",
            )

    workspace = _resolve_active_workspace()
    relative_path, destination = build_workspace_attachment_destination(
        session_id=session_id,
        filename=decoded_filename or "attachment",
        content_type=content_type,
        workspace=workspace,
    )

    written = 0
    try:
        with destination.open("wb") as output:
            async for chunk in req.stream():
                if not chunk:
                    continue
                written += len(chunk)
                if written > MAX_CHAT_ATTACHMENT_SIZE:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"Attachment exceeds max size {MAX_CHAT_ATTACHMENT_SIZE} bytes",
                    )
                output.write(chunk)
    except HTTPException:
        destination.unlink(missing_ok=True)
        raise
    except Exception as exc:
        destination.unlink(missing_ok=True)
        logger.exception(f"Failed to upload attachment for session {session_id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload attachment",
        ) from exc

    if written <= 0:
        destination.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty attachment body",
        )

    item = build_attachment_item(
        relative_path=relative_path,
        absolute_path=destination,
        content_type=content_type,
    )
    return AttachmentItemResponse(**item)


@router.post("/send", response_model=SendMessageResponse)
async def send_message(
    request: SendMessageRequest,
    req: Request,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """
    发送消息到 Agent 并获取 SSE 流式响应。
    
    客户端监听 'message' 事件接收响应片段。
    """
    try:
        normalized_message = _validate_message_or_attachments(request.message, request.attachments)
        session = await _require_session(db, request.session_id)
        runtime_config = resolve_session_runtime_config(config_loader.config, session)
        workspace = _resolve_active_workspace()
        resolved_attachments = _resolve_attachment_inputs(request.attachments, workspace)
        attachment_items = build_attachment_items_from_workspace(resolved_attachments)
        attachment_paths = [relative_path for relative_path, _ in resolved_attachments]
        
        # 保存用户消息到数据库
        session_manager = SessionManager(db)
        user_message = await session_manager.add_message(
            session_id=request.session_id,
            role="user",
            content=normalized_message,
            message_context=build_message_context(attachment_items=attachment_items),
        )
        
        if user_message is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save user message"
            )
        
        logger.info(
            f"Processing message for session {request.session_id}: "
            f"{normalized_message[:50]}..."
        )

        # 创建会话专属的 AgentLoop（支持会话级配置）
        agent_loop = await get_agent_loop(req, db, session_id=request.session_id)
        explicit_external_request = _resolve_explicit_external_tool_request(
            agent_loop,
            normalized_message,
        )
        explicit_team_request = _resolve_explicit_team_workflow_request(
            agent_loop,
            normalized_message,
        )

        context_service = ConversationContextService(db)
        context_payload = await context_service.build_model_context(
            session_id=request.session_id,
            max_history_messages=runtime_config.persona_config.max_history_messages,
            enable_short_context_summary=runtime_config.persona_config.enable_short_context_summary,
        )
        context = context_payload.history
        
        # 排除刚添加的用户消息(因为 process_message 会添加)
        if context and context[-1].get("role") == "user":
            context = context[:-1]

        from backend.modules.agent.task_manager import CancellationToken
        cancel_token = CancellationToken()
        
        # 创建流式响应生成器
        async def event_stream() -> AsyncIterator[str]:
            """SSE 事件流生成器"""
            assistant_content = ""
            assistant_reasoning = ""
            
            try:
                # 发送开始事件
                yield f"event: start\ndata: {json.dumps({'message_id': str(user_message.id)})}\n\n"

                if explicit_external_request:
                    profile_name, _task = explicit_external_request
                    logger.info(
                        "Routing web chat explicit external-agent request through agent loop: "
                        f"profile={profile_name}, session={request.session_id}"
                    )
                    context_for_processing = _inject_explicit_external_request_context(
                        agent_loop,
                        context,
                        explicit_external_request,
                    )
                else:
                    context_for_processing = context

                if explicit_team_request is not None:
                    team_name, goal = explicit_team_request
                    agent_loop.tools.set_session_id(request.session_id)
                    agent_loop.tools.set_channel("web-chat")
                    agent_loop.tools.set_cancel_token(cancel_token)

                    if normalized_message.strip() == "/team":
                        assistant_content = build_team_command_overview(
                            getattr(agent_loop, "context_builder", None),
                            log_scope="web chat explicit team command",
                        )
                    elif not team_name:
                        assistant_content = build_team_command_overview(
                            getattr(agent_loop, "context_builder", None),
                            log_scope="web chat explicit team command",
                        )
                    elif not goal:
                        assistant_content = build_team_goal_usage(team_name)
                    else:
                        logger.info(
                            "Routing web chat directly to workflow_run: "
                            f"team={team_name}, session={request.session_id}"
                        )
                        assistant_content = await agent_loop.tools.execute(
                            tool_name="workflow_run",
                            arguments={
                                "team_name": team_name,
                                "goal": goal,
                            },
                        )

                    yield f"event: message\ndata: {json.dumps({'content': assistant_content})}\n\n"
                    await asyncio.sleep(0)
                else:
                    prefer_direct_workflow_result = False
                    team_finder = getattr(agent_loop.context_builder, "_find_mentioned_team", None)
                    if callable(team_finder):
                        try:
                            prefer_direct_workflow_result = bool(team_finder(normalized_message))
                        except Exception as exc:
                            logger.warning(f"Failed to detect mentioned team for SSE chat: {exc}")

                    pending_reasoning_chunks: List[str] = []

                    async def reasoning_event_handler(reasoning_chunk: str) -> None:
                        nonlocal assistant_reasoning
                        assistant_reasoning += reasoning_chunk or ""
                        if reasoning_chunk:
                            pending_reasoning_chunks.append(reasoning_chunk)

                    async for chunk in agent_loop.process_message(
                        message=normalized_message,
                        session_id=request.session_id,
                        context=context_for_processing,
                        session_summary=context_payload.session_summary,
                        media=attachment_paths,
                        channel="web-chat",
                        cancel_token=cancel_token,
                        reasoning_event_handler=reasoning_event_handler,
                        prefer_direct_workflow_result=prefer_direct_workflow_result,
                    ):
                        while pending_reasoning_chunks:
                            reasoning_chunk = pending_reasoning_chunks.pop(0)
                            yield (
                                "event: reasoning\n"
                                f"data: {json.dumps({'content': reasoning_chunk}, ensure_ascii=False)}\n\n"
                            )

                        assistant_content += chunk

                        # 发送内容块
                        yield f"event: message\ndata: {json.dumps({'content': chunk})}\n\n"

                        # 确保立即发送
                        await asyncio.sleep(0)

                    while pending_reasoning_chunks:
                        reasoning_chunk = pending_reasoning_chunks.pop(0)
                        yield (
                            "event: reasoning\n"
                            f"data: {json.dumps({'content': reasoning_chunk}, ensure_ascii=False)}\n\n"
                        )

                # 保存助手响应到数据库
                persisted_content, normalized_reasoning, used_reasoning_fallback = (
                    normalize_assistant_persistence_payload(
                        assistant_content,
                        assistant_reasoning,
                    )
                )
                assistant_message_context = (
                    build_message_context(reasoning_content=normalized_reasoning)
                )

                if persisted_content:
                    if used_reasoning_fallback:
                        yield (
                            "event: message\n"
                            f"data: {json.dumps({'content': persisted_content}, ensure_ascii=False)}\n\n"
                        )
                        await asyncio.sleep(0)

                    assistant_message = await session_manager.add_message(
                        session_id=request.session_id,
                        role="assistant",
                        content=persisted_content,
                        message_context=assistant_message_context,
                    )

                    try:
                        from backend.modules.tools.conversation_history import get_conversation_history
                        conversation_history = get_conversation_history()
                        await conversation_history.backfill_message_id(
                            session_id=request.session_id,
                            message_id=assistant_message.id,
                        )
                    except Exception as backfill_err:
                        logger.warning(f"Failed to backfill tool conversations for session {request.session_id}: {backfill_err}")

                    schedule_context_maintenance(
                        db_session_factory=get_db_session_factory(),
                        session_id=request.session_id,
                        max_history_messages=runtime_config.persona_config.max_history_messages,
                        enable_short_context_summary=runtime_config.persona_config.enable_short_context_summary,
                        provider=agent_loop.provider,
                        model=runtime_config.model_name,
                        memory_store=getattr(agent_loop.context_builder, "memory", None),
                        auto_summary_source="web-chat",
                    )
                    
                    # 发送完成事件
                    yield f"event: done\ndata: {json.dumps({'message_id': str(assistant_message.id)})}\n\n"
                else:
                    # 没有内容，发送空完成事件
                    yield f"event: done\ndata: {json.dumps({'message_id': None})}\n\n"
                
            except asyncio.CancelledError:
                cancel_token.cancel()
                raise
            except Exception as e:
                logger.exception(f"Error in event stream: {e}")
                
                # 发送错误事件
                error_data = {
                    "error": str(e),
                    "type": type(e).__name__,
                }
                yield f"event: error\ndata: {json.dumps(error_data)}\n\n"
            finally:
                if agent_loop.tools:
                    agent_loop.tools.set_cancel_token(None)
        
        # 返回 SSE 流式响应
        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
            },
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to send message: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process message: {str(e)}"
        )


@router.get("/sessions", response_model=List[SessionResponse])
async def list_sessions(
    limit: Optional[int] = None,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
) -> List[SessionResponse]:
    """
    获取所有会话列表
    
    Args:
        limit: 返回数量限制（可选）
        offset: 偏移量
        db: 数据库会话
        
    Returns:
        List[SessionResponse]: 会话列表
    """
    try:
        session_manager = SessionManager(db)
        sessions = await session_manager.list_sessions(limit=limit, offset=offset)
        
        return [
            SessionResponse(
                id=session.id,
                name=session.name,
                created_at=to_utc_iso(session.created_at),
                updated_at=to_utc_iso(session.updated_at),
                summary=session.summary,
                summary_updated_at=to_utc_iso(session.summary_updated_at),
            )
            for session in sessions
        ]
        
    except Exception as e:
        logger.exception(f"Failed to list sessions: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list sessions: {str(e)}"
        )


@router.post("/sessions", response_model=SessionResponse)
async def create_session(
    name: str,
    db: AsyncSession = Depends(get_db),
) -> SessionResponse:
    """
    创建新会话
    
    Args:
        name: 会话名称
        db: 数据库会话
        
    Returns:
        SessionResponse: 创建的会话
    """
    try:
        session_manager = SessionManager(db)
        session = await session_manager.create_session(name=name)
        
        return SessionResponse(
            id=session.id,
            name=session.name,
            created_at=to_utc_iso(session.created_at),
            updated_at=to_utc_iso(session.updated_at),
        )
        
    except Exception as e:
        logger.exception(f"Failed to create session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create session: {str(e)}"
        )


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, bool]:
    """
    删除会话
    
    Args:
        session_id: 会话 ID
        db: 数据库会话
        
    Returns:
        dict: 删除结果
        
    Raises:
        HTTPException: 会话不存在
    """
    try:
        session_manager = SessionManager(db)
        success = await session_manager.delete_session(session_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session '{session_id}' not found"
            )
        
        return {"success": True}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to delete session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete session: {str(e)}"
        )


class UpdateSessionRequest(BaseModel):
    """更新会话请求"""
    name: str


@router.put("/sessions/{session_id}", response_model=SessionResponse)
async def update_session(
    session_id: str,
    request: UpdateSessionRequest,
    db: AsyncSession = Depends(get_db),
) -> SessionResponse:
    """
    更新会话信息
    
    Args:
        session_id: 会话 ID
        request: 更新请求（包含新的会话名称）
        db: 数据库会话
        
    Returns:
        SessionResponse: 更新后的会话
        
    Raises:
        HTTPException: 会话不存在
    """
    try:
        session_manager = SessionManager(db)
        session = await session_manager.update_session(session_id, name=request.name)
        
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session '{session_id}' not found"
            )
        
        return SessionResponse(
            id=session.id,
            name=session.name,
            created_at=to_utc_iso(session.created_at),
            updated_at=to_utc_iso(session.updated_at),
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to update session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update session: {str(e)}"
        )


@router.get("/sessions/{session_id}/messages", response_model=List[MessageResponse])
async def get_session_messages(
    session_id: str,
    limit: Optional[int] = None,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
) -> List[MessageResponse]:
    """
    获取会话的消息列表（包含工具调用记录）
    
    Args:
        session_id: 会话 ID
        limit: 返回数量限制（可选）
        offset: 偏移量
        db: 数据库会话
        
    Returns:
        List[MessageResponse]: 消息列表（包含关联的工具调用）
        
    Raises:
        HTTPException: 会话不存在
    """
    try:
        from sqlalchemy import select
        from backend.models.tool_conversation import ToolConversation
        
        # 获取全局 subagent_manager
        subagent_mgr = get_global_subagent_manager()
        
        session_manager = SessionManager(db)
        
        # 验证会话是否存在
        session = await session_manager.get_session(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session '{session_id}' not found"
            )
        
        # 获取消息
        messages = await session_manager.get_messages(
            session_id=session_id,
            limit=limit,
            offset=offset,
        )
        
        # 创建有效消息 ID 集合（用于过滤孤立的工具调用记录）
        valid_message_ids = {msg.id for msg in messages}
        
        # 获取该会话的所有工具调用记录（只获取有效的）
        # 过滤条件：message_id 为 NULL（会话级）或 message_id 在有效消息列表中
        tool_calls_query = (
            select(ToolConversation)
            .where(ToolConversation.session_id == session_id)
            .where(
                (ToolConversation.message_id.is_(None)) |
                (ToolConversation.message_id.in_(valid_message_ids))
            )
            .order_by(ToolConversation.timestamp.asc())
        )
        
        tool_calls_result = await db.execute(tool_calls_query)
        all_tool_calls = tool_calls_result.scalars().all()
        
        # 按 message_id 分组工具调用
        tool_calls_by_message: Dict[int, List[ToolConversation]] = {}
        for tc in all_tool_calls:
            if tc.message_id is not None:
                if tc.message_id not in tool_calls_by_message:
                    tool_calls_by_message[tc.message_id] = []
                tool_calls_by_message[tc.message_id].append(tc)
        
        # 构建响应，包含工具调用
        response_messages = []
        for msg in messages:
            # 获取该消息关联的工具调用
            msg_tool_calls = tool_calls_by_message.get(msg.id, [])
            
            # 转换工具调用为响应格式
            tool_call_responses = []
            for tc in msg_tool_calls:
                logger.info(f"Tool call: {tc.tool_name}, ID: {tc.id}")
                try:
                    arguments = json.loads(tc.arguments) if tc.arguments else {}
                except json.JSONDecodeError:
                    arguments = {}
                
                # 确定状态
                status_value = "success"
                if tc.error:
                    status_value = "error"
                
                # 为 spawn 工具调用添加任务详情
                spawn_task = None
                logger.info(f"Checking spawn: tool_name={tc.tool_name}, subagent_mgr={subagent_mgr is not None}")
                if tc.tool_name == "spawn" and subagent_mgr:
                    logger.info(f"Processing spawn tool call: {tc.id}")
                    try:
                        # 从 result 字段提取 task_id
                        task_id = None
                        if tc.result:
                            # result 格式: "子 Agent [label] 已启动 (ID: task_id)。..." 或 "子 Agent [label] 已完成 (ID: task_id)。..."
                            match = re.search(r'\(ID: ([a-f0-9\-]+)\)', tc.result)
                            if match:
                                task_id = match.group(1)
                                logger.info(f"Found spawn task_id: {task_id}")
                        
                        if task_id:
                            # 先从内存查询
                            task = subagent_mgr.get_task(task_id)
                            if task:
                                logger.debug(f"Found spawn task in memory: {task_id}")
                                spawn_task = task.to_dict()
                            else:
                                # 内存中没有，从数据库查询
                                logger.debug(f"Task not in memory, querying database: {task_id}")
                                from sqlalchemy import select
                                from backend.models.task import Task as TaskModel
                                
                                result = await db.execute(
                                    select(TaskModel).where(TaskModel.id == task_id)
                                )
                                db_task = result.scalar_one_or_none()
                                
                                if db_task:
                                    logger.debug(f"Found spawn task in database: {task_id}")
                                    # 从数据库任务构建 spawn_task
                                    tool_call_records = []
                                    if db_task.tool_call_records:
                                        try:
                                            tool_call_records = json.loads(db_task.tool_call_records)
                                            logger.debug(f"Loaded {len(tool_call_records)} tool call records")
                                        except json.JSONDecodeError as e:
                                            logger.warning(f"Failed to parse tool_call_records: {e}")
                                    
                                    spawn_task = {
                                        "task_id": db_task.id,
                                        "label": db_task.label,
                                        "message": db_task.message,
                                        "session_id": db_task.session_id,
                                        "status": db_task.status,
                                        "progress": db_task.progress,
                                        "result": db_task.result,
                                        "error": db_task.error,
                                        "created_at": to_utc_iso(db_task.created_at),
                                        "started_at": to_utc_iso(db_task.started_at),
                                        "completed_at": to_utc_iso(db_task.completed_at),
                                        "tool_call_records": tool_call_records,
                                    }
                                else:
                                    logger.warning(f"Spawn task not found in database: {task_id}")
                    except Exception as e:
                        logger.warning(f"Failed to get spawn task details: {e}", exc_info=True)
                
                tool_call_responses.append(
                    ToolCallResponse(
                        id=tc.id,
                        name=tc.tool_name,
                        arguments=arguments,
                        result=tc.result,
                        error=tc.error,
                        status=status_value,
                        duration=tc.duration_ms,
                        spawn_task=spawn_task,
                    )
                )
            
            response_messages.append(
                MessageResponse(
                    id=msg.id,
                    session_id=msg.session_id,
                    role=msg.role,
                    content=msg.content,
                    reasoning_content=_extract_reasoning_content_from_message_context(
                        getattr(msg, "message_context", None)
                    ),
                    attachment_items=[
                        AttachmentItemResponse(**item)
                        for item in _extract_attachment_items_from_message_context(
                            getattr(msg, "message_context", None)
                        )
                    ],
                    created_at=to_utc_iso(msg.created_at),
                    tool_calls=tool_call_responses,
                )
            )
        
        return response_messages
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get messages: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get messages: {str(e)}"
        )


@router.delete("/sessions/{session_id}/messages/{message_id}")
async def delete_single_message(
    session_id: str,
    message_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    删除单条消息及其关联的工具调用记录
    
    Args:
        session_id: 会话 ID
        message_id: 消息 ID
        db: 数据库会话
        
    Returns:
        dict: 操作结果（包含删除的工具调用记录数量）
        
    Raises:
        HTTPException: 会话或消息不存在
    """
    try:
        session_manager = SessionManager(db)
        
        # 验证会话是否存在
        session = await session_manager.get_session(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session '{session_id}' not found"
            )
        
        # 验证消息是否存在且属于该会话
        from sqlalchemy import select
        from backend.models.message import Message
        
        result = await db.execute(
            select(Message).where(
                Message.id == message_id,
                Message.session_id == session_id
            )
        )
        message = result.scalar_one_or_none()
        
        if message is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Message '{message_id}' not found in session '{session_id}'"
            )
        
        # 使用 SessionManager 的 delete_message 方法（会自动清理工具调用记录）
        success = await session_manager.delete_message(message_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to delete message {message_id}"
            )
        
        logger.info(f"Deleted message {message_id} from session {session_id}")
        
        return {
            "success": True,
            "message": f"Message {message_id} and its tool conversations deleted"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to delete message: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete message: {str(e)}"
        )


@router.delete("/sessions/{session_id}/messages")
async def clear_session_messages(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    清空会话的所有消息
    
    Args:
        session_id: 会话 ID
        db: 数据库会话
        
    Returns:
        dict: 操作结果
        
    Raises:
        HTTPException: 会话不存在或清空失败
    """
    try:
        session_manager = SessionManager(db)
        
        # 验证会话是否存在
        session = await session_manager.get_session(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session '{session_id}' not found"
            )
        
        # 清空消息
        await session_manager.clear_messages(session_id)
        
        logger.info(f"Cleared all messages for session: {session_id}")
        
        return {
            "success": True,
            "message": f"All messages cleared for session {session_id}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to clear messages: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear messages: {str(e)}"
        )


@router.get("/sessions/{session_id}/export")
async def export_session_context(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    agent_loop: AgentLoop = Depends(get_agent_loop),
) -> dict:
    """
    导出会话的完整上下文（包括系统提示词、工具定义、所有消息和工具调用历史）
    
    导出内容：
    1. 系统提示词（发送给 LLM 的完整上下文）
    2. 工具定义（所有可用工具的描述和参数）
    3. 用户消息和 AI 回复（数据库中保存的内容）
    4. 工具执行历史（从工具历史记录中获取）
    
    Args:
        session_id: 会话 ID
        db: 数据库会话
        agent_loop: Agent 循环实例
        
    Returns:
        dict: 包含系统提示词、工具定义、消息和工具历史的完整上下文
        
    Raises:
        HTTPException: 会话不存在
    """
    try:
        session_manager = SessionManager(db)
        
        # 验证会话是否存在
        session = await session_manager.get_session(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session '{session_id}' not found"
            )
        
        # 获取所有消息
        messages = await session_manager.get_messages(session_id=session_id)
        
        # 构建系统提示词
        system_prompt = agent_loop.context_builder.build_system_prompt()
        
        # 获取工具定义
        tool_definitions = []
        if agent_loop.tools:
            tool_definitions = agent_loop.tools.get_definitions()
        
        # 构建消息历史
        message_history = []
        for msg in messages:
            message_history.append({
                "id": msg.id,
                "role": msg.role,
                "content": msg.content,
                "created_at": to_utc_iso(msg.created_at),
            })
        
        # 获取工具执行历史（从工具注册表）
        tool_history = []
        if agent_loop.tools and hasattr(agent_loop.tools, 'history'):
            # 过滤出属于当前会话的工具调用
            for record in agent_loop.tools.history:
                # 工具历史记录可能没有 session_id，所以我们导出所有记录
                # 并在前端/导出文件中标注这是全局工具历史
                tool_history.append({
                    "tool": record.get("tool"),
                    "arguments": record.get("arguments"),
                    "result": record.get("result"),
                    "error": record.get("error"),
                    "success": record.get("success"),
                    "duration": record.get("duration"),
                    "timestamp": to_utc_iso(record.get("timestamp")),
                })
        
        return {
            "session_id": session_id,
            "session_name": session.name,
            "system_prompt": system_prompt,
            "tool_definitions": tool_definitions,
            "messages": message_history,
            "tool_history": tool_history,
            "exported_at": to_utc_iso(datetime.now(timezone.utc)),
            "note": "此导出包含完整的系统提示词和工具定义。工具调用历史为全局记录，可能包含其他会话的工具调用。"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to export session context: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export session context: {str(e)}"
        )


# ============================================================================
# Session Summary Endpoints
# ============================================================================


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> SessionResponse:
    """
    获取会话详情（包含总结）
    
    Args:
        session_id: 会话 ID
        db: 数据库会话
        
    Returns:
        SessionResponse: 会话详情
        
    Raises:
        HTTPException: 会话不存在
    """
    try:
        context_service = ConversationContextService(db)
        session = await context_service.get_session(session_id)
        
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session '{session_id}' not found"
            )
        
        return SessionResponse(
            id=session.id,
            name=session.name,
            created_at=to_utc_iso(session.created_at),
            updated_at=to_utc_iso(session.updated_at),
            summary=session.summary,
            summary_updated_at=to_utc_iso(session.summary_updated_at),
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get session: {str(e)}"
        )


@router.put("/sessions/{session_id}/summary")
async def update_session_summary(
    session_id: str,
    request: UpdateSessionSummaryRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    更新会话总结
    
    Args:
        session_id: 会话 ID
        request: 更新总结请求
        db: 数据库会话
        
    Returns:
        dict: 更新结果
        
    Raises:
        HTTPException: 会话不存在
    """
    try:
        context_service = ConversationContextService(db)
        session = await context_service.update_session_summary(
            session_id,
            request.summary,
        )

        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session '{session_id}' not found"
            )
        
        logger.info(f"Updated summary for session {session_id}")
        await _notify_webui_session_updated(session_id)
        
        return {
            "success": True,
            "session_id": session_id,
            "summary": session.summary,
            "updated_at": to_utc_iso(session.summary_updated_at),
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to update session summary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update session summary: {str(e)}"
        )


@router.delete("/sessions/{session_id}/summary")
async def delete_session_summary(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    删除会话总结
    
    Args:
        session_id: 会话 ID
        db: 数据库会话
        
    Returns:
        dict: 删除结果
        
    Raises:
        HTTPException: 会话不存在
    """
    try:
        context_service = ConversationContextService(db)
        session = await context_service.clear_session_summary(session_id)

        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session '{session_id}' not found"
            )
        
        logger.info(f"Deleted summary for session {session_id}")
        await _notify_webui_session_updated(session_id)
        
        return {"success": True, "session_id": session_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to delete session summary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete session summary: {str(e)}"
        )


@router.post("/sessions/{session_id}/summarize", response_model=SummarizeSessionResponse)
async def summarize_session_to_memory(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    agent_loop: AgentLoop = Depends(get_agent_loop),
) -> SummarizeSessionResponse:
    """总结会话内容并保存到长期记忆
    
    使用 LLM 直接总结对话为一行记忆条目，写入 MEMORY.md。
    
    Args:
        session_id: 会话 ID
        db: 数据库会话
        agent_loop: Agent 循环实例
        
    Returns:
        SummarizeSessionResponse: 总结结果
    """
    try:
        from sqlalchemy import select
        from backend.models.session import Session
        from pathlib import Path
        from backend.modules.agent.analyzer import MessageAnalyzer
        from backend.modules.agent.prompts import CONVERSATION_TO_MEMORY_PROMPT
        
        logger.info(f"Starting memory summarization for session {session_id}")
        
        # 1. 验证会话
        result = await db.execute(
            select(Session).where(Session.id == session_id)
        )
        session = result.scalar_one_or_none()
        
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session '{session_id}' not found"
            )
        
        # 2. 获取消息
        session_manager = SessionManager(db)
        messages = await session_manager.get_messages(session_id=session_id)
        
        if not messages or len(messages) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Session has no messages to summarize"
            )
        
        # 3. 格式化消息
        analyzer = MessageAnalyzer()
        message_dicts = [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]
        formatted = analyzer.format_messages_for_summary(message_dicts, max_chars=4000)
        
        # 4. 用 LLM 生成总结
        prompt = CONVERSATION_TO_MEMORY_PROMPT.format(messages=formatted)
        
        summary_content = ""
        async for chunk in agent_loop.provider.chat_stream(
            messages=[{"role": "user", "content": prompt}],
            model=agent_loop.model,
            temperature=0.3,
        ):
            if chunk.is_content and chunk.content:
                summary_content += chunk.content
        
        summary = summary_content.strip()
        
        # 5. 如果 LLM 认为无需记录，直接返回
        if "无需记录" in summary:
            return SummarizeSessionResponse(
                success=True,
                summary=summary,
                message="对话无需记录到长期记忆",
            )
        
        # 6. 写入记忆
        config = config_loader.config
        workspace = Path(config.workspace.path) if config.workspace.path else WORKSPACE_DIR
        memory_dir = workspace / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)
        memory = MemoryStore(memory_dir)
        
        # 确定来源 - 使用渠道标识而非会话名称
        source = "web-chat"
        line_num = memory.append_entry(source=source, content=summary)
        
        logger.info(f"Memory saved at line {line_num}: {summary[:80]}...")
        
        return SummarizeSessionResponse(
            success=True,
            summary=summary,
            message=f"已保存到记忆第 {line_num} 行（共 {memory.get_line_count()} 条）",
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to summarize session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to summarize session: {str(e)}"
        )


# ============================================================================
# Session Configuration Endpoints
# ============================================================================


class SessionConfigRequest(BaseModel):
    """会话配置请求"""
    model: Optional[Dict[str, Any]] = Field(None, alias='model_config')
    persona: Optional[Dict[str, Any]] = Field(None, alias='persona_config')
    
    class Config:
        populate_by_name = True


class SessionConfigResponse(BaseModel):
    """会话配置响应"""
    session_id: str
    use_custom_config: bool
    model: Dict[str, Any] = Field(..., alias='model_config')
    persona: Dict[str, Any] = Field(..., alias='persona_config')
    global_defaults: Dict[str, Any]
    
    class Config:
        populate_by_name = True


@router.get("/sessions/{session_id}/config", response_model=SessionConfigResponse)
async def get_session_config(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> SessionConfigResponse:
    """获取会话配置
    
    返回会话的有效配置（如果有自定义配置则合并，否则返回全局默认）
    
    Args:
        session_id: 会话 ID
        db: 数据库会话
        
    Returns:
        SessionConfigResponse: 会话配置
        
    Raises:
        HTTPException: 会话不存在
    """
    try:
        from sqlalchemy import select
        from backend.models.session import Session
        
        # 获取会话
        result = await db.execute(
            select(Session).where(Session.id == session_id)
        )
        session = result.scalar_one_or_none()
        
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session '{session_id}' not found"
            )
        
        config = config_loader.config
        runtime_config = resolve_session_runtime_config(config, session)
        global_defaults = resolve_session_runtime_config(config, None)
        
        return SessionConfigResponse(
            session_id=session_id,
            use_custom_config=session.use_custom_config,
            model_config=runtime_config.model_response,
            persona_config=runtime_config.persona_response,
            global_defaults={
                "model": global_defaults.model_response,
                "persona": global_defaults.persona_response,
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get session config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get session config: {str(e)}"
        )


@router.put("/sessions/{session_id}/config")
async def update_session_config(
    session_id: str,
    request: SessionConfigRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """更新会话配置
    
    Args:
        session_id: 会话 ID
        request: 配置更新请求
        db: 数据库会话
        
    Returns:
        dict: 更新结果
        
    Raises:
        HTTPException: 会话不存在或配置无效
    """
    try:
        from sqlalchemy import select
        from backend.models.session import Session
        
        # 获取会话
        result = await db.execute(
            select(Session).where(Session.id == session_id)
        )
        session = result.scalar_one_or_none()
        
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session '{session_id}' not found"
            )
        
        # 更新配置
        if request.model is not None:
            normalized_model = _normalize_session_model_overrides(dict(request.model))
            session.session_model_config = json.dumps(
                normalized_model,
                ensure_ascii=False,
            )
        
        if request.persona is not None:
            normalized_persona = _normalize_session_persona_overrides(dict(request.persona))
            session.session_persona_config = json.dumps(
                normalized_persona,
                ensure_ascii=False,
            )
        
        session.use_custom_config = True
        session.updated_at = datetime.now(timezone.utc)
        
        await db.commit()
        await db.refresh(session)
        
        logger.info(f"Updated config for session {session_id}")
        await _notify_webui_session_updated(session_id)
        
        return {
            "success": True,
            "session_id": session_id,
            "message": "Session configuration updated"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to update session config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update session config: {str(e)}"
        )


@router.delete("/sessions/{session_id}/config")
async def reset_session_config(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """重置会话配置为全局默认
    
    Args:
        session_id: 会话 ID
        db: 数据库会话
        
    Returns:
        dict: 重置结果
        
    Raises:
        HTTPException: 会话不存在
    """
    try:
        from sqlalchemy import select
        from backend.models.session import Session
        
        result = await db.execute(
            select(Session).where(Session.id == session_id)
        )
        session = result.scalar_one_or_none()
        
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session '{session_id}' not found"
            )
        
        session.session_model_config = None
        session.session_persona_config = None
        session.use_custom_config = False
        session.updated_at = datetime.now(timezone.utc)
        
        await db.commit()
        
        logger.info(f"Reset config for session {session_id}")
        await _notify_webui_session_updated(session_id)
        
        return {
            "success": True,
            "session_id": session_id,
            "message": "Session configuration reset to global defaults"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to reset session config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset session config: {str(e)}"
        )
