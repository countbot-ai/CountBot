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
    SESSION_MODEL_SOURCE_SESSION_PANEL,
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
    SessionWorkspaceConfig,
    SessionWorkspaceRequest,
    SummarizeSessionResponse,
    ToolCallResponse,
    UpdateSessionRequest,
    UpdateSessionSummaryRequest,
)
from backend.modules.workspace import (
    get_global_workspace_path,
    resolve_session_workspace,
    validate_session_workspace_path,
)

@router.get("/sessions/{session_id}/config", response_model=SessionConfigResponse)
async def get_session_config(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(require_active_user),
) -> SessionConfigResponse:
    """获取会话配置，有自定义配置时合并，否则返回全局默认。"""
    try:
        from sqlalchemy import select
        from backend.models.session import Session
        
        # 获取会话
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
        
        config = config_loader.config
        runtime_config = resolve_session_runtime_config(config, session)
        global_defaults = resolve_session_runtime_config(config, None)

        from backend.modules.multiuser.identity import resolve_chat_mode_for_user

        runtime_config.chat_mode = resolve_chat_mode_for_user(
            user, runtime_config.chat_mode
        )
        runtime_config.model_response["chat_mode"] = runtime_config.chat_mode
        
        # 仅统计生效的自定义配置，已移除的模型绑定不计入
        has_effective_custom_config = bool(
            runtime_config.has_custom_model_config or runtime_config.has_custom_persona_config
        )

        persona_payload = runtime_config.persona_response
        global_persona_payload = global_defaults.persona_response
        global_model_payload = global_defaults.model_response
        if not getattr(user, "is_admin", False):
            # 管理员全局人设里的称呼、地址与主动问候不下发给普通用户（与
            # resolve_persona_for_user 的既有约定一致）；基底换成用户自身人设，
            # 再叠加会话面板显式写入的字段。
            from backend.modules.multiuser.effective import resolve_persona_for_user

            user_persona = (await resolve_persona_for_user(user)).model_dump()
            session_view = dict(user_persona)
            for key, value in (runtime_config.persona_overrides or {}).items():
                if value is None or key not in session_view:
                    continue
                if key == "heartbeat" and isinstance(value, dict):
                    merged_heartbeat = dict(session_view.get("heartbeat") or {})
                    merged_heartbeat.update(
                        {k: v for k, v in value.items() if v is not None}
                    )
                    session_view["heartbeat"] = merged_heartbeat
                else:
                    session_view[key] = value
            persona_payload = session_view
            global_persona_payload = user_persona

            # 「全局默认模型」只能是普通用户自己的默认绑定：不能把管理员的
            # 全局 provider/model 绑定下发给普通用户。
            from backend.modules.multiuser.effective import (
                resolve_model_for_user,
                resolved_stream_enabled,
            )

            try:
                resolved = await resolve_model_for_user(user)
                user_provider, user_model = resolved.provider_id, resolved.model_id
                user_stream_enabled = resolved_stream_enabled(
                    resolved, fallback=config.model.stream_enabled
                )
            except Exception:
                user_provider, user_model = "", ""
                user_stream_enabled = None
            global_model_payload = {
                **global_model_payload,
                "provider": user_provider,
                "model": user_model,
                "api_key": "",
                "api_base": "",
            }
            # 会话未显式设置输出模式时，面板回显用户自己模型的实际取值，
            # 避免展示管理员全局值导致「看起来改了其实没改」
            if user_stream_enabled is not None and runtime_config.stream_override is None:
                global_model_payload["stream_enabled"] = user_stream_enabled
                runtime_config.model_response["stream_enabled"] = user_stream_enabled

        return SessionConfigResponse(
            session_id=session_id,
            use_custom_config=has_effective_custom_config,
            model_config=runtime_config.model_response,
            persona_config=persona_payload,
            global_defaults={
                "model": global_model_payload,
                "persona": global_persona_payload,
            },
            workspace=(
                SessionWorkspaceConfig(
                    path=session.workspace_path,
                    effective_path=str(resolve_session_workspace(session)),
                    global_path=str(get_global_workspace_path()),
                )
                if getattr(user, "is_admin", False)
                # 普通用户不暴露工作空间自定义字段，只回显其私有生效路径
                else SessionWorkspaceConfig(
                    path=None,
                    effective_path=str(resolve_session_workspace(session, user)),
                    global_path=None,
                )
            ),
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
    user: AuthUser = Depends(require_active_user),
) -> dict:
    """更新会话配置。"""
    try:
        from sqlalchemy import select
        from backend.models.session import Session
        
        # 获取会话
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
        
        # 更新配置
        if request.model is not None:
            raw_model = dict(request.model)
            # 普通用户不得在会话里写供应商凭据：api_key/api_base 只在设置页维护
            if not getattr(user, "is_admin", False):
                raw_model.pop("api_key", None)
                raw_model.pop("api_base", None)
            normalized_model = _normalize_session_model_overrides(raw_model)
            if normalized_model:
                # 仅带来源标记的绑定视为用户显式设置，其余使用全局默认模型
                normalized_model["source"] = SESSION_MODEL_SOURCE_SESSION_PANEL
                from backend.modules.multiuser.identity import resolve_chat_mode_for_user

                normalized_model["chat_mode"] = resolve_chat_mode_for_user(
                    user, normalized_model.get("chat_mode")
                )
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
        await _notify_webui_session_updated(session_id, owner_scope(user))
        
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

@router.put("/sessions/{session_id}/workspace")
async def update_session_workspace(
    session_id: str,
    request: SessionWorkspaceRequest,
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(require_active_user),
) -> dict:
    """设置或清除会话级工作空间，自定义路径须为已存在的绝对目录。管理员专属。"""
    if not getattr(user, "is_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="普通用户不能自定义会话工作区",
        )
    try:
        from sqlalchemy import select
        from backend.models.session import Session

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

        raw_path = (request.path or "").strip()
        if not raw_path:
            session.workspace_path = None
        else:
            try:
                resolved = validate_session_workspace_path(raw_path)
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=str(exc),
                ) from exc
            session.workspace_path = str(resolved)

        session.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(session)

        logger.info(
            f"Updated workspace for session {session_id}: "
            f"{session.workspace_path or 'global'}"
        )
        await _notify_webui_session_updated(session_id, owner_scope(user))

        return {
            "success": True,
            "session_id": session_id,
            "workspace_path": session.workspace_path,
            "effective_workspace_path": str(resolve_session_workspace(session)),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to update session workspace: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update session workspace: {str(e)}"
        )


@router.delete("/sessions/{session_id}/config")
async def reset_session_config(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(require_active_user),
) -> dict:
    """将会话配置重置为全局默认。"""
    try:
        from sqlalchemy import select
        from backend.models.session import Session
        
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
        
        session.session_model_config = None
        session.session_persona_config = None
        session.use_custom_config = False
        # 重置为全局默认时，会话工作空间也一并恢复跟随全局
        session.workspace_path = None
        session.updated_at = datetime.now(timezone.utc)
        
        await db.commit()
        
        logger.info(f"Reset config for session {session_id}")
        await _notify_webui_session_updated(session_id, owner_scope(user))
        
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
