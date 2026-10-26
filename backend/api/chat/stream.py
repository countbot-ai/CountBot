"""消息发送：SSE 流式响应。"""

import asyncio
import json
import re
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db, get_db_session_factory
from backend.modules.agent.context import ContextBuilder
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
from backend.modules.session import (
    ConversationContextService,
    build_session_model_override,
    resolve_session_runtime_config,
    schedule_context_maintenance,
)
from backend.modules.session.message_context import (
    build_attachment_items_from_workspace,
    build_message_context,
)

from backend.api.chat._router import router
from backend.api.chat.loop_factory import get_agent_loop
from backend.modules.session.manager import SessionManager
from backend.modules.session.message_context import normalize_assistant_persistence_payload
from backend.utils.datetime_utils import to_utc_iso
from backend.modules.agent.session_gate import get_session_gate
from backend.modules.tools.execution import (
    ExecutionState,
    ToolExecutionInProgress,
    ToolExecutionRejected,
)
from backend.modules.tools.conversation_history import get_conversation_history

from backend.api.chat.helpers import (
    _inject_explicit_external_request_context,
    _resolve_explicit_external_tool_request,
    _resolve_explicit_team_workflow_request,
    MAX_TOOL_PREVIEW_LIMIT,
    _build_tool_call_response,
    _clamp_tool_preview_limit,
    _extract_attachment_items_from_message_context,
    _extract_reasoning_content_from_message_context,
    _load_spawn_task_detail,
    _normalize_session_model_overrides,
    _normalize_session_persona_overrides,
    _notify_webui_session_updated,
    _resolve_active_workspace,
    _resolve_attachment_inputs,
    _require_session,
    _truncate_text,
    _validate_message_or_attachments,
)
from backend.api.chat.models import (
    SendMessageResponse,
    AttachmentItemResponse,
    MessageResponse,
    MessageToolCallPageResponse,
    PreviewRequest,
    SendMessageRequest,
    SessionConfigRequest,
    SessionConfigResponse,
    SessionResponse,
    SummarizeSessionResponse,
    ToolCallResponse,
    UpdateSessionRequest,
    UpdateSessionSummaryRequest,
)

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

        from backend.ws.connection import acquire_cancel_token, cleanup_cancel_token

        # 创建流式响应生成器
        async def event_stream() -> AsyncIterator[str]:
            """SSE 事件流生成器"""
            assistant_content = ""
            assistant_reasoning = ""
            direct_workflow_non_success = False
            turn_gate = get_session_gate()
            turn_acquired = False
            # 登记到会话取消令牌表：此前令牌仅在 WS 链路登记，
            # /api/queue/cancel 与 /stop 无法中止 HTTP SSE 这条处理
            cancel_token, token_created = acquire_cancel_token(request.session_id)

            try:
                # 会话串行准入放在生成器内部：HTTP 响应一旦返回而客户端未真正读取，
                # 生成器不会执行，也就不会占用会话；放在生成器外会留下无法释放的锁。
                await turn_gate.acquire(request.session_id)
                turn_acquired = True

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
                        # 此直连路径绕过 AgentLoop，直接消费 Registry 的结构化结果；
                        # display_text 只用于 SSE 展示及既有助手消息记录。
                        workflow_outcome = await agent_loop.tools.execute_outcome(
                            tool_name="workflow_run",
                            arguments={
                                "team_name": team_name,
                                "goal": goal,
                            },
                            cancellation_token=cancel_token,
                        )
                        if not isinstance(workflow_outcome, (ToolExecutionInProgress, ToolExecutionRejected)):
                            # SSE 直连路径绕过 AgentLoop，收到 Registry 终态后补记同一投影。
                            from backend.modules.tools.file_audit_logger import file_audit_logger
                            file_audit_logger.record_outcome(
                                workflow_outcome, source="sse_workflow",
                                session_id=request.session_id,
                            )
                        assistant_content = workflow_outcome.display_text
                        if isinstance(workflow_outcome, ToolExecutionInProgress):
                            # 准入结果表示原 operation 仍在运行，不发送完成事件。
                            direct_workflow_non_success = True
                            yield (
                                "event: tool_progress\n"
                                f"data: {json.dumps({'content': assistant_content}, ensure_ascii=False)}\n\n"
                            )
                        elif isinstance(workflow_outcome, ToolExecutionRejected):
                            direct_workflow_non_success = True
                            yield (
                                "event: error\n"
                                f"data: {json.dumps({'error': assistant_content, 'type': workflow_outcome.reason}, ensure_ascii=False)}\n\n"
                            )
                        elif workflow_outcome.state is not ExecutionState.SUCCEEDED:
                            direct_workflow_non_success = True
                            if workflow_outcome.state is ExecutionState.UNKNOWN_OUTCOME:
                                assistant_content = (
                                    "Tool outcome is unknown; side effects may have occurred. "
                                    + assistant_content
                                )
                            yield (
                                "event: error\n"
                                f"data: {json.dumps({'error': assistant_content, 'type': workflow_outcome.state.value}, ensure_ascii=False)}\n\n"
                            )

                    if not direct_workflow_non_success:
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
                        enable_auto_memory_summary=config_loader.config.injection.auto_memory_summary,
                    )
                    
                    # 发送完成事件
                    if not direct_workflow_non_success:
                        yield f"event: done\ndata: {json.dumps({'message_id': str(assistant_message.id)})}\n\n"
                else:
                    # 没有内容，发送空完成事件
                    if not direct_workflow_non_success:
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
                if turn_acquired:
                    turn_gate.release(request.session_id)
                # 仅清理自己登记的令牌，避免摘掉同会话其他链路正在使用的那个
                if token_created:
                    cleanup_cancel_token(request.session_id, cancel_token)
        
        # 结束本请求已开启的读事务：流式响应可能持续数分钟（慢上游），
        # 请求级会话会一直活到流结束；若此时挂着未结束的读事务，
        # 在非 WAL 模式下会一直占着共享锁，把其它写请求全部堵死。
        if db is not None:
            await db.commit()

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
