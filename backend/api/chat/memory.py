"""会话摘要、上下文导出与记忆沉淀。"""

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
from backend.utils.datetime_utils import to_utc_iso
from backend.modules.agent.loop import AgentLoop
from backend.modules.agent.memory import MemoryStore
from backend.utils.paths import WORKSPACE_DIR

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
        from backend.modules.agent.prompts import CONVERSATION_TO_MEMORY_PROMPT, render_prompt
        
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
        
        # 5. 如果 LLM 认为无需记录，直接返回
        from backend.modules.agent.prompts import is_memory_noop

        if is_memory_noop(summary):
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
