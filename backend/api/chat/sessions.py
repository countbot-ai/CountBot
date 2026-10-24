"""会话的增删改查。"""

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
