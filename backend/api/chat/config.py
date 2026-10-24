"""会话级配置：模型、人设覆盖与重置。"""

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
