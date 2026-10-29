"""请求预览：查看一次请求实际会发给模型的内容。"""

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

@router.post("/preview")
async def preview_request(
    payload: PreviewRequest,
    req: Request,
    db: AsyncSession = Depends(get_db),
):
    """预览一次请求实际会发给模型的内容。

    用于排查注入类问题：可以直接看到 system prompt 由哪些区块组成、每块受哪个
    开关控制、首条用户消息里是否追加了动态上下文，以及当前会带上哪些工具定义。

    本接口不写入数据库、不调用模型，只做构建。
    """
    from backend.modules.agent.request_preview import build_request_preview

    session = await _require_session(db, payload.session_id)
    runtime_config = resolve_session_runtime_config(config_loader.config, session)
    agent_loop = await get_agent_loop(req, db, session_id=payload.session_id)

    context_service = ConversationContextService(db)
    context_payload = await context_service.build_model_context(
        session_id=payload.session_id,
        max_history_messages=runtime_config.persona_config.max_history_messages,
        enable_short_context_summary=runtime_config.persona_config.enable_short_context_summary,
    )
    history = context_payload.history
    if history and history[-1].get("role") == "user":
        history = history[:-1]

    return build_request_preview(
        agent_loop.context_builder,
        message=payload.message or "",
        history=history,
        session_summary=context_payload.session_summary,
        media=payload.attachments or None,
        channel=payload.channel or "web-chat",
        chat_id=payload.session_id,
        persona_config=runtime_config.persona_config,
        tool_registry=agent_loop.tools,
        # 传入实际生效的额度，保持预览与真实请求一致
        tool_budget=runtime_config.max_iterations,
    )
