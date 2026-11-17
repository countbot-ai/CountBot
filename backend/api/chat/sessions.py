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
from backend.modules.multiuser.identity import AuthUser
from backend.modules.multiuser.permissions import owner_scope, require_active_user
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


def _to_session_response(session) -> SessionResponse:
    """统一补齐会话工作空间字段，避免各接口各自解析。"""
    from backend.modules.workspace import resolve_session_workspace

    return SessionResponse(
        id=session.id,
        name=session.name,
        created_at=to_utc_iso(session.created_at),
        updated_at=to_utc_iso(session.updated_at),
        summary=session.summary,
        summary_updated_at=to_utc_iso(session.summary_updated_at),
        workspace_path=session.workspace_path,
        effective_workspace_path=str(resolve_session_workspace(session)),
    )


@router.get("/sessions", response_model=List[SessionResponse])
async def list_sessions(
    limit: Optional[int] = None,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(require_active_user),
) -> List[SessionResponse]:
    """获取会话列表。"""
    try:
        session_manager = SessionManager(db, owner_id=owner_scope(user))
        sessions = await session_manager.list_sessions(limit=limit, offset=offset)
        
        return [_to_session_response(session) for session in sessions]
        
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
    user: AuthUser = Depends(require_active_user),
) -> SessionResponse:
    """创建新会话。"""
    try:
        session_manager = SessionManager(db, owner_id=owner_scope(user))
        session = await session_manager.create_session(name=name)
        
        return _to_session_response(session)
        
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
    user: AuthUser = Depends(require_active_user),
) -> Dict[str, bool]:
    """删除会话。"""
    try:
        session_manager = SessionManager(db, owner_id=owner_scope(user))
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
    user: AuthUser = Depends(require_active_user),
) -> SessionResponse:
    """更新会话信息。"""
    try:
        session_manager = SessionManager(db, owner_id=owner_scope(user))
        session = await session_manager.update_session(session_id, name=request.name)
        
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session '{session_id}' not found"
            )
        
        return _to_session_response(session)
        
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
    user: AuthUser = Depends(require_active_user),
) -> SessionResponse:
    """获取会话详情，包含总结。"""
    try:
        session = await _require_session(db, session_id, owner_scope(user))
        
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session '{session_id}' not found"
            )
        
        return _to_session_response(session)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get session: {str(e)}"
        )
