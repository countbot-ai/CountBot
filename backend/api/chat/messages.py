"""消息查询：消息列表、工具调用记录、单条删除与清空。"""

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
from backend.api.chat.helpers import (
    DEFAULT_TOOL_PREVIEW_LIMIT,
    SPECIAL_HISTORY_TOOL_NAMES,
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
from backend.api.chat.state import get_global_subagent_manager
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

@router.get("/sessions/{session_id}/messages", response_model=List[MessageResponse])
async def get_session_messages(
    session_id: str,
    limit: Optional[int] = None,
    offset: int = 0,
    tool_mode: Literal["full", "summary", "none"] = "full",
    tool_preview_limit: int = Query(
        DEFAULT_TOOL_PREVIEW_LIMIT,
        ge=120,
        le=MAX_TOOL_PREVIEW_LIMIT,
    ),
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
        from sqlalchemy import func, select
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
        
        tool_call_counts: Dict[int, int] = {}
        special_tool_names_by_message: Dict[int, List[str]] = {}
        tool_calls_by_message: Dict[int, List[ToolConversation]] = {}
        if messages:
            valid_message_ids = {msg.id for msg in messages}

            count_query = (
                select(
                    ToolConversation.message_id,
                    func.count(ToolConversation.id),
                )
                .where(ToolConversation.session_id == session_id)
                .where(ToolConversation.message_id.in_(valid_message_ids))
                .group_by(ToolConversation.message_id)
            )
            count_result = await db.execute(count_query)
            tool_call_counts = {
                int(message_id): int(total)
                for message_id, total in count_result.all()
                if message_id is not None
            }

            special_tool_query = (
                select(ToolConversation.message_id, ToolConversation.tool_name)
                .where(ToolConversation.session_id == session_id)
                .where(ToolConversation.message_id.in_(valid_message_ids))
                .where(ToolConversation.tool_name.in_(SPECIAL_HISTORY_TOOL_NAMES))
                .order_by(ToolConversation.timestamp.asc())
            )
            special_tool_result = await db.execute(special_tool_query)
            for message_id, tool_name in special_tool_result.all():
                if message_id is None or not tool_name:
                    continue
                bucket = special_tool_names_by_message.setdefault(int(message_id), [])
                if tool_name not in bucket:
                    bucket.append(str(tool_name))

            if tool_mode != "none":
                preview_limit = _clamp_tool_preview_limit(tool_preview_limit)
                tool_calls_query = (
                    select(ToolConversation)
                    .where(ToolConversation.session_id == session_id)
                    .where(ToolConversation.message_id.in_(valid_message_ids))
                    .order_by(ToolConversation.timestamp.asc())
                )

                tool_calls_result = await db.execute(tool_calls_query)
                all_tool_calls = tool_calls_result.scalars().all()

                for tc in all_tool_calls:
                    if tc.message_id is not None:
                        tool_calls_by_message.setdefault(tc.message_id, []).append(tc)
            else:
                preview_limit = DEFAULT_TOOL_PREVIEW_LIMIT
        else:
            preview_limit = DEFAULT_TOOL_PREVIEW_LIMIT
        
        # 构建响应，包含工具调用
        response_messages = []
        for msg in messages:
            # 获取该消息关联的工具调用
            msg_tool_calls = tool_calls_by_message.get(msg.id, [])
            
            # 转换工具调用为响应格式
            tool_call_responses = []
            for tc in msg_tool_calls:
                tool_call_responses.append(
                    await _build_tool_call_response(
                        tc=tc,
                        db=db,
                        subagent_mgr=subagent_mgr,
                        tool_mode=tool_mode,
                        preview_limit=preview_limit,
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
                    tool_call_count=tool_call_counts.get(msg.id, 0),
                    special_tool_call_names=special_tool_names_by_message.get(msg.id, []),
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

@router.get(
    "/sessions/{session_id}/messages/{message_id}/tool-calls",
    response_model=MessageToolCallPageResponse,
)
async def get_message_tool_calls(
    session_id: str,
    message_id: int,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    tool_mode: Literal["full", "summary"] = "summary",
    tool_preview_limit: int = Query(
        DEFAULT_TOOL_PREVIEW_LIMIT,
        ge=120,
        le=MAX_TOOL_PREVIEW_LIMIT,
    ),
    db: AsyncSession = Depends(get_db),
) -> MessageToolCallPageResponse:
    """分页获取单条消息关联的工具调用。"""
    try:
        from sqlalchemy import func, select
        from backend.models.message import Message
        from backend.models.tool_conversation import ToolConversation

        subagent_mgr = get_global_subagent_manager()
        session_manager = SessionManager(db)

        session = await session_manager.get_session(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session '{session_id}' not found",
            )

        message_result = await db.execute(
            select(Message)
            .where(Message.id == message_id)
            .where(Message.session_id == session_id)
        )
        message = message_result.scalar_one_or_none()
        if message is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Message '{message_id}' not found in session '{session_id}'",
            )

        total_result = await db.execute(
            select(func.count(ToolConversation.id))
            .where(ToolConversation.session_id == session_id)
            .where(ToolConversation.message_id == message_id)
        )
        total = int(total_result.scalar_one() or 0)

        preview_limit = _clamp_tool_preview_limit(tool_preview_limit)
        tool_calls_result = await db.execute(
            select(ToolConversation)
            .where(ToolConversation.session_id == session_id)
            .where(ToolConversation.message_id == message_id)
            .order_by(ToolConversation.timestamp.asc())
            .limit(limit)
            .offset(offset)
        )
        tool_calls = tool_calls_result.scalars().all()

        items: List[ToolCallResponse] = []
        for tc in tool_calls:
            items.append(
                await _build_tool_call_response(
                    tc=tc,
                    db=db,
                    subagent_mgr=subagent_mgr,
                    tool_mode=tool_mode,
                    preview_limit=preview_limit,
                )
            )

        return MessageToolCallPageResponse(
            message_id=message_id,
            total=total,
            offset=offset,
            limit=limit,
            has_more=offset + len(items) < total,
            items=items,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get message tool calls: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get message tool calls: {str(e)}"
        )

@router.get("/tool-calls/{tool_call_id}", response_model=ToolCallResponse)
async def get_tool_call_detail(
    tool_call_id: str,
    db: AsyncSession = Depends(get_db),
) -> ToolCallResponse:
    """按需获取单条工具调用的完整详情。"""
    try:
        from sqlalchemy import select
        from backend.models.tool_conversation import ToolConversation

        subagent_mgr = get_global_subagent_manager()
        result = await db.execute(
            select(ToolConversation).where(ToolConversation.id == tool_call_id)
        )
        tool_call = result.scalar_one_or_none()
        if tool_call is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tool call '{tool_call_id}' not found",
            )

        return await _build_tool_call_response(
            tc=tool_call,
            db=db,
            subagent_mgr=subagent_mgr,
            tool_mode="full",
            preview_limit=DEFAULT_TOOL_PREVIEW_LIMIT,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get tool call detail: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get tool call detail: {str(e)}"
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
