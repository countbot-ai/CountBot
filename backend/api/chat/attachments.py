"""聊天附件的上传与下载，以及工作区文件下载。"""

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
    build_attachment_item,
    build_attachment_items_from_workspace,
    build_workspace_attachment_destination,
    build_message_context,
)

from backend.api.chat._router import router
from backend.api.chat.helpers import (
    MAX_CHAT_ATTACHMENT_SIZE,
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

@router.get("/sessions/{session_id}/attachments/{attachment_path:path}")
async def download_chat_attachment(
    session_id: str,
    attachment_path: str,
    db: AsyncSession = Depends(get_db),
):
    """获取/下载会话附件文件。"""
    from fastapi.responses import FileResponse
    import mimetypes

    await _require_session(db, session_id)

    workspace = _resolve_active_workspace()
    safe_path = attachment_path.strip().replace("\\", "/")
    resolved_file = (workspace / safe_path).resolve()

    try:
        relative = resolved_file.relative_to(workspace)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Attachment path is outside workspace",
        ) from exc

    session_prefix = str(Path("uploads") / "chat" / session_id)
    if not str(relative).startswith(session_prefix):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Attachment does not belong to this session",
        )

    if not resolved_file.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment not found",
        )

    mime_type, _ = mimetypes.guess_type(resolved_file.name)
    return FileResponse(
        resolved_file,
        media_type=mime_type or "application/octet-stream",
        filename=resolved_file.name,
    )

@router.get("/sessions/{session_id}/workspace/{file_path:path}")
async def download_workspace_file(
    session_id: str,
    file_path: str,
    db: AsyncSession = Depends(get_db),
):
    """获取/下载工作区文件（供 send_media 等工具的参数预览使用）。"""
    from fastapi.responses import FileResponse
    import mimetypes

    await _require_session(db, session_id)

    workspace = _resolve_active_workspace()
    safe_path = file_path.strip().replace("\\", "/")
    resolved_file = (workspace / safe_path).resolve()

    try:
        resolved_file.relative_to(workspace)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="File path is outside workspace",
        ) from exc

    if not resolved_file.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )

    if resolved_file.stat().st_size > 50 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large to serve",
        )

    mime_type, _ = mimetypes.guess_type(resolved_file.name)
    return FileResponse(
        resolved_file,
        media_type=mime_type or "application/octet-stream",
        filename=resolved_file.name,
    )

@router.get("/workspace/{file_path:path}")
async def download_workspace_file_public(
    file_path: str,
):
    """获取/下载工作区文件（无需 session 校验，供 send_media 工具预览使用）。"""
    from fastapi.responses import FileResponse
    import mimetypes

    workspace = _resolve_active_workspace()
    safe_path = file_path.strip().replace("\\", "/")
    resolved_file = (workspace / safe_path).resolve()

    try:
        resolved_file.relative_to(workspace)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="File path is outside workspace",
        ) from exc

    if not resolved_file.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )

    if resolved_file.stat().st_size > 50 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large to serve",
        )

    mime_type, _ = mimetypes.guess_type(resolved_file.name)
    return FileResponse(
        resolved_file,
        media_type=mime_type or "application/octet-stream",
        filename=resolved_file.name,
    )
