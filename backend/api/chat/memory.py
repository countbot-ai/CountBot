"""会话摘要、上下文导出与记忆沉淀。"""

import asyncio
import json
import re
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
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

from backend.modules.multiuser.identity import AuthUser
from backend.modules.multiuser.permissions import owner_scope, require_active_user
from backend.api.chat._router import router
from backend.api.chat.loop_factory import get_user_agent_loop
from backend.modules.session.manager import SessionManager
from backend.utils.datetime_utils import to_utc_iso
from backend.modules.agent.loop import AgentLoop
from backend.modules.agent.memory import MemoryStore
from backend.modules.memory import Confidence


def _resolve_session_source(session: Any) -> str:
    """会话记忆的写入来源：渠道会话保留原渠道，否则记为 web-chat。"""
    raw = getattr(session, "channel_context", None)
    if raw:
        try:
            decoded = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, ValueError):
            decoded = None
        if isinstance(decoded, dict):
            channel = str(decoded.get("channel") or "").strip()
            if channel:
                return channel
    return "web-chat"

from backend.api.chat.helpers import (
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

@router.get("/sessions/{session_id}/export")
async def export_session_context(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    agent_loop: AgentLoop = Depends(get_user_agent_loop),
    user: AuthUser = Depends(require_active_user),
) -> dict:
    """导出会话完整上下文，含系统提示词、工具定义与消息历史。"""
    try:
        session_manager = SessionManager(db, owner_id=owner_scope(user))
        
        session = await session_manager.get_session(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session '{session_id}' not found"
            )
        
        messages = await session_manager.get_messages(session_id=session_id)
        
        system_prompt = agent_loop.context_builder.build_system_prompt()
        
        tool_definitions = []
        if agent_loop.tools:
            tool_definitions = agent_loop.tools.get_definitions()
        
        message_history = []
        for msg in messages:
            message_history.append({
                "id": msg.id,
                "role": msg.role,
                "content": msg.content,
                "created_at": to_utc_iso(msg.created_at),
            })
        
        tool_history = []
        if agent_loop.tools and hasattr(agent_loop.tools, 'history'):
            # 工具历史不含 session_id，无法按会话过滤，故全部导出
            for record in agent_loop.tools.history:
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

@router.put("/sessions/{session_id}/summary")
async def update_session_summary(
    session_id: str,
    request: UpdateSessionSummaryRequest,
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(require_active_user),
) -> dict:
    """更新会话总结。"""
    try:
        await _require_session(db, session_id, owner_scope(user))

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
        await _notify_webui_session_updated(session_id, owner_scope(user))
        
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
    user: AuthUser = Depends(require_active_user),
) -> dict:
    """删除会话总结。"""
    try:
        # 归属校验：普通用户只能清空自己的会话摘要
        await _require_session(db, session_id, owner_scope(user))

        context_service = ConversationContextService(db)
        session = await context_service.clear_session_summary(session_id)

        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session '{session_id}' not found"
            )
        
        logger.info(f"Deleted summary for session {session_id}")
        await _notify_webui_session_updated(session_id, owner_scope(user))
        
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
    agent_loop: AgentLoop = Depends(get_user_agent_loop),
    user: AuthUser = Depends(require_active_user),
) -> SummarizeSessionResponse:
    """总结会话内容并写入长期记忆，重复总结不产生重复条目。"""
    try:
        from sqlalchemy import select
        from backend.models.session import Session
        from pathlib import Path
        from backend.modules.agent.analyzer import MessageAnalyzer
        from backend.modules.agent.prompts import CONVERSATION_TO_MEMORY_PROMPT, render_prompt
        
        logger.info(f"Starting memory summarization for session {session_id}")
        
        query = select(Session).where(Session.id == session_id)
        scope = owner_scope(user)
        if scope:
            query = query.where(Session.owner_id == scope)
        result = await db.execute(query)
        session = result.scalar_one_or_none()
        
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session '{session_id}' not found"
            )
        
        session_manager = SessionManager(db, owner_id=owner_scope(user))
        messages = await session_manager.get_messages(session_id=session_id)
        
        if not messages or len(messages) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Session has no messages to summarize"
            )
        
        analyzer = MessageAnalyzer()
        message_dicts = [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]
        formatted = analyzer.format_messages_for_summary(message_dicts, max_chars=4000)
        
        prompt = render_prompt(CONVERSATION_TO_MEMORY_PROMPT, messages=formatted)
        
        summary_content = ""
        async for chunk in agent_loop.provider.chat_stream(
            messages=[{"role": "user", "content": prompt}],
            model=agent_loop.model,
            temperature=0.3,
        ):
            if chunk.is_content and chunk.content:
                summary_content += chunk.content
        
        summary = summary_content.strip()
        
        from backend.modules.agent.prompts import is_memory_noop

        if is_memory_noop(summary):
            return SummarizeSessionResponse(
                success=True,
                summary=summary,
                message="对话无需记录到长期记忆",
            )
        
        # 记忆必须落在当前用户自己的工作区：普通用户不能写进管理员全局目录，
        # 也不能把自己的会话摘要混进管理员记忆。
        from backend.modules.workspace import resolve_user_workspace

        workspace = resolve_user_workspace(user)
        memory_dir = workspace / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)
        memory = MemoryStore(memory_dir)

        # 来源取会话渠道，无渠道上下文时才记为网页来源
        source = _resolve_session_source(session)
        # 摘要由模型对历史复述而来，属于推断内容，只能进冷存档
        line_num = memory.append_entry(
            source=source,
            content=summary,
            confidence=Confidence.INFERRED,
        )
        
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
