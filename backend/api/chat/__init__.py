"""
Chat API。

子模块：state 进程级共享状态；models 请求与响应模型；helpers 辅助函数；
loop_factory AgentLoop 装配；attachments 附件；preview 请求预览；stream
SSE 流式发送；sessions 会话；messages 消息；config 会话级配置；memory
摘要与导出。

全局 SubagentManager 集中在 state，本模块转发 get/set，保证 app.py、
api/tasks.py、api/tools.py 读到同一实例。
"""

from backend.api.chat._router import router
from backend.api.chat.helpers import (
    MAX_CHAT_ATTACHMENT_SIZE,
    _inject_explicit_external_request_context,
    _prepare_external_task,
    _resolve_explicit_external_tool_request,
    _resolve_explicit_team_workflow_request,
    MAX_TOOL_PREVIEW_LIMIT,
    SPECIAL_HISTORY_TOOL_NAMES,
    _build_tool_call_response,
    _clamp_tool_preview_limit,
    _extract_attachment_items_from_message_context,
    _extract_reasoning_content_from_message_context,
    _extract_spawn_task_id,
    _load_spawn_task_detail,
    _normalize_api_mode,
    _normalize_session_model_overrides,
    _normalize_session_persona_overrides,
    _notify_webui_session_updated,
    _parse_tool_arguments,
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
    SendMessageResponse,
    SessionConfigRequest,
    SessionConfigResponse,
    SessionResponse,
    SummarizeSessionResponse,
    ToolCallResponse,
    UpdateSessionRequest,
    UpdateSessionSummaryRequest,
)
from backend.api.chat.state import (
    get_global_subagent_manager,
    set_global_subagent_manager,
)

# 导入路由模块以完成 @router.xxx 注册（副作用导入，不能省略）
from backend.api.chat import attachments as _attachments  # noqa: F401
from backend.api.chat import config as _config  # noqa: F401
from backend.api.chat import memory as _memory  # noqa: F401
from backend.api.chat import messages as _messages  # noqa: F401
from backend.api.chat import preview as _preview  # noqa: F401
from backend.api.chat import sessions as _sessions  # noqa: F401
from backend.api.chat import stream as _stream  # noqa: F401

from backend.api.chat.attachments import (
    download_chat_attachment,
    download_workspace_file,
    download_workspace_file_public,
    upload_chat_attachment,
)
from backend.api.chat.config import (
    get_session_config,
    reset_session_config,
    update_session_config,
)
from backend.api.chat.loop_factory import get_agent_loop
from backend.api.chat.memory import (
    delete_session_summary,
    export_session_context,
    summarize_session_to_memory,
    update_session_summary,
)
from backend.api.chat.messages import (
    clear_session_messages,
    delete_single_message,
    get_message_tool_calls,
    get_session_messages,
    get_tool_call_detail,
)
from backend.api.chat.preview import preview_request
from backend.api.chat.sessions import (
    create_session,
    delete_session,
    get_session,
    list_sessions,
    update_session,
)
from backend.api.chat.stream import send_message

__all__ = [
    "router",
    "get_agent_loop",
    "send_message",
    "preview_request",
    "list_sessions",
    "create_session",
    "get_session",
    "update_session",
    "delete_session",
    "get_session_messages",
    "get_message_tool_calls",
    "get_tool_call_detail",
    "delete_single_message",
    "clear_session_messages",
    "export_session_context",
    "update_session_summary",
    "delete_session_summary",
    "summarize_session_to_memory",
    "get_session_config",
    "update_session_config",
    "reset_session_config",
    "upload_chat_attachment",
    "download_chat_attachment",
    "download_workspace_file",
    "download_workspace_file_public",
    "set_global_subagent_manager",
    "get_global_subagent_manager",
]
