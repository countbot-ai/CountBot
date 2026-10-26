"""频道入站消息工具：从 handler.py 拆出的纯函数（@mention 清洗、会话路由、上下文编解码、错误友好化与 provider 校验），handler 按原名导入使用。"""

import json
import re
from typing import Dict, List, Optional

from loguru import logger

from backend.models.message import Message
from backend.modules.channels.base import InboundMessage
from backend.modules.config.loader import config_loader
from backend.modules.providers.runtime import (
    build_provider_unavailable_message,
    get_provider_runtime_state,
)
from backend.modules.session.message_context import (
    extract_reasoning_content_from_message_context,
    normalize_assistant_persistence_payload,
    strip_workflow_exec_metadata,
)

# 飞书格式 @_user_数字；企业微信/钉钉格式 <at user_id="xxx">@用户名</at>
_AT_MENTION_RE = re.compile(r"@_user_\d+\s*|<at[^>]*>.*?</at>\s*", re.IGNORECASE)
# 纯文本唤醒 mention（如客户端展开后的 "@SBot "）；仅移除开头连续前缀，避免误删正文中的 @账号/邮箱。
_LEADING_WAKEUP_MENTION_TOKEN_RE = re.compile(
    r"^(?:@|＠)(?P<name>[^\s@＠]{1,64})(?:[\s\u3000,:：，、;；]+|\s*$)",
    re.IGNORECASE,
)
# 工作流执行元数据注释（用于前端面板持久化，频道输出时需剥离）
_WORKFLOW_META_RE = re.compile(r"<!--WORKFLOW_EXEC:.*?:WORKFLOW_EXEC-->", re.DOTALL)

_PRIMARY_GROUP_SHARED_CHANNELS = {"wecom", "feishu", "dingtalk", "qq"}
_PRIMARY_ACCOUNT_ID = "default"


def _friendly_channel_error(raw: str) -> str:
    """将原始异常信息转换为频道用户可读的友好提示。"""
    lower = raw.lower()
    if any(k in lower for k in ("429", "余额", "quota", "rate limit", "资源包", "充值")):
        return "AI 服务额度不足，请联系管理员检查 API 账户余额。"
    if any(k in lower for k in ("401", "unauthorized", "api_key", "authentication")):
        return "API 认证失败，请联系管理员检查密钥配置。"
    if any(k in lower for k in ("timeout", "connection", "network", "ssl")):
        return "网络连接异常，请稍后重试。"
    if any(k in lower for k in ("context length", "too long", "context_length_exceeded")):
        return "对话上下文过长，请发送 /new 创建新会话后重试。"
    if any(k in lower for k in ("500", "502", "503", "504", "service unavailable")):
        return "AI 服务暂时不可用，请稍后重试。"
    return "处理消息时出错，请稍后重试。"


def _validate_runtime_provider(runtime_config) -> None:
    """确保渠道消息不会使用禁用或未完成配置的 provider。"""

    runtime_state = get_provider_runtime_state(
        config_loader.config,
        runtime_config.provider_name,
        api_key_override=runtime_config.api_key,
        api_base_override=runtime_config.api_base,
    )
    if not runtime_state.selectable:
        raise RuntimeError(
            build_provider_unavailable_message(
                runtime_config.provider_name,
                runtime_state.reason,
            )
        )


def _normalize_channel_inbound_content(msg: InboundMessage) -> str:
    """清理渠道层唤醒 mention，避免干扰后续语义理解。"""
    content = _AT_MENTION_RE.sub("", msg.content).strip()

    if msg.channel not in {"wecom", "dingtalk", "feishu"}:
        return content

    if not _is_group_message(msg) or not content:
        return content

    active_team_names = _load_active_team_names()
    normalized = content
    stripped_mentions: List[str] = []

    while normalized:
        match = _LEADING_WAKEUP_MENTION_TOKEN_RE.match(normalized)
        if not match:
            break
        mention_name = str(match.group("name") or "").strip()
        if mention_name in active_team_names:
            break
        stripped_mentions.append(mention_name)
        normalized = normalized[match.end():].strip()

    if stripped_mentions:
        logger.debug(
            f"[{msg.channel}] Stripped leading wakeup mention(s): "
            f"{stripped_mentions!r}, {content[:80]!r} -> {normalized[:80]!r}"
        )
    return normalized


def _load_active_team_names() -> set[str]:
    """读取当前激活团队名称，用于保留用户显式的 @团队名 指令。"""
    try:
        from backend.database import SessionLocal
        from backend.models.agent_team import AgentTeam
        from sqlalchemy import select

        with SessionLocal() as session:
            result = session.execute(
                select(AgentTeam.name).where(AgentTeam.is_active == True)  # noqa: E712
            )
            return {
                str(name).strip()
                for name in result.scalars().all()
                if str(name).strip()
            }
    except Exception as e:
        logger.warning(f"Failed to load active team names for mention normalization: {e}")
        return set()


def _safe_text(value: object) -> str:
    text = str(value or "").strip()
    return text


def _is_group_message(msg: InboundMessage) -> bool:
    metadata = msg.metadata or {}

    if msg.channel == "wecom":
        raw_chat_id = _safe_text(metadata.get("chatid") or msg.chat_id)
        sender_from_meta = _safe_text(((metadata.get("from") or {}).get("userid")) or msg.sender_id)
        return bool(raw_chat_id and sender_from_meta and raw_chat_id != sender_from_meta)
    if msg.channel == "dingtalk":
        return bool(metadata.get("is_group"))
    if msg.channel == "feishu":
        return _safe_text(metadata.get("chat_type")).lower() == "group"
    if msg.channel == "qq":
        return bool(metadata.get("is_group"))
    return False


def _resolve_group_chat_id(msg: InboundMessage) -> str:
    metadata = msg.metadata or {}

    if msg.channel == "wecom":
        return _safe_text(metadata.get("chatid") or msg.chat_id)
    if msg.channel == "dingtalk":
        return _safe_text(metadata.get("conversation_id") or msg.chat_id)
    return _safe_text(msg.chat_id)


def _resolve_sender_name(msg: InboundMessage) -> str:
    metadata = msg.metadata or {}
    if msg.channel == "wecom":
        return _safe_text(metadata.get("sender_name") or ((metadata.get("from") or {}).get("name")) or msg.sender_id)
    return _safe_text(metadata.get("sender_name") or msg.sender_id)


def _format_bot_label(account_id: str) -> str:
    if account_id == _PRIMARY_ACCOUNT_ID:
        return "主机器人"
    return f"机器人[{account_id}]"


def _resolve_session_route(msg: InboundMessage) -> Dict[str, object]:
    metadata = msg.metadata or {}
    source_account_id = _safe_text(metadata.get("account_id") or _PRIMARY_ACCOUNT_ID) or _PRIMARY_ACCOUNT_ID
    is_group = _is_group_message(msg)
    group_chat_id = _resolve_group_chat_id(msg)
    supports_primary_group_shared = msg.channel in _PRIMARY_GROUP_SHARED_CHANNELS
    use_primary_group_context = bool(
        supports_primary_group_shared
        and is_group
        and source_account_id == _PRIMARY_ACCOUNT_ID
    )
    context_owner_account_id = (
        _PRIMARY_ACCOUNT_ID if use_primary_group_context else source_account_id
    )
    session_scope = (
        "group_shared_primary"
        if use_primary_group_context
        else ("group_independent" if is_group else "private_independent")
    )
    # 飞书话题群：同一 chat 下按 thread_id 拆成独立会话，回复仍走原 chat。
    topic_key = ""
    if msg.channel == "feishu" and is_group:
        topic_key = _safe_text(metadata.get("thread_id") or metadata.get("root_id"))
    session_chat_id = group_chat_id if is_group else _safe_text(msg.chat_id)
    if topic_key:
        session_chat_id = f"{session_chat_id}#topic:{topic_key}"

    return {
        "channel": msg.channel,
        "is_group": is_group,
        "group_chat_id": group_chat_id,
        "session_chat_id": session_chat_id,
        "thread_id": topic_key or None,
        "source_account_id": source_account_id,
        "reply_account_id": source_account_id,
        "context_owner_account_id": context_owner_account_id,
        "primary_account_id": _PRIMARY_ACCOUNT_ID,
        "supports_primary_group_shared": supports_primary_group_shared,
        "use_primary_group_context": use_primary_group_context,
        "session_scope": session_scope,
        "sender_id": _safe_text(msg.sender_id),
        "sender_name": _resolve_sender_name(msg),
        "target_bot_label": _format_bot_label(source_account_id),
        "reply_bot_label": _format_bot_label(source_account_id),
        "context_owner_bot_label": _format_bot_label(context_owner_account_id),
    }


def _encode_message_context(message_context: Optional[dict]) -> Optional[str]:
    if not message_context:
        return None
    return json.dumps(message_context, ensure_ascii=False)


def _decode_message_context(raw: Optional[str]) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _format_message_for_model(role: str, content: str, message_context: Optional[dict]) -> str:
    if not message_context or not message_context.get("is_group"):
        return content

    sender_name = _safe_text(message_context.get("sender_name") or message_context.get("sender_id")) or "未知用户"
    target_bot_label = _safe_text(message_context.get("target_bot_label")) or "机器人"
    session_scope = _safe_text(message_context.get("session_scope"))

    if role == "user":
        scope_label = "主机器人群上下文" if session_scope == "group_shared_primary" else "独立机器人群会话"
        return (
            f"[群聊消息][{scope_label}][发送者:{sender_name}][目标:{target_bot_label}]\n"
            f"{content}"
        )
    if role == "assistant":
        # 助手历史只保留纯文本，避免模型把内部机器人标签复述到实际回复里。
        return content
    return content


def _build_history_message(message: Message) -> dict:
    """把数据库消息转换为模型可用的历史条目（与 Web 端一致：剥离 workflow 元数据并还原思考内容）。"""
    raw_message_context = getattr(message, "message_context", None)
    message_context = _decode_message_context(raw_message_context)
    entry = {
        "role": message.role,
        "content": strip_workflow_exec_metadata(
            _format_message_for_model(message.role, message.content, message_context)
        ),
    }
    # 该函数只接受原始 JSON 字符串（内部自行 json.loads），不能传解码后的 dict
    reasoning = extract_reasoning_content_from_message_context(raw_message_context)
    if reasoning:
        entry["reasoning_content"] = reasoning
    return entry


def _normalize_assistant_output(
    content: Optional[str],
    reasoning_content: Optional[str] = None,
) -> tuple[str, str]:
    normalized_content, normalized_reasoning, _ = normalize_assistant_persistence_payload(
        content,
        reasoning_content,
    )
    return normalized_content, str(normalized_reasoning or "")
