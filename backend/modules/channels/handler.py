"""频道消息处理器模块

处理来自所有频道的入站消息，集成 Agent 循环进行回复。
与 WebSocket 端共享 context_builder / subagent_manager / tool_params，
确保频道和网页 UI 使用完全一致的提示词、技能、工具。
"""

import asyncio
import json
import re
import time
from pathlib import Path
from typing import Dict, List, Optional

from loguru import logger

from backend.database import get_db_session_factory
from backend.models.message import Message
from backend.models.session import Session
from backend.modules.agent.context import ContextBuilder
from backend.modules.agent.loop import AgentLoop
from backend.modules.agent.task_manager import CancellationToken
from backend.modules.agent.team_commands import (
    build_team_command_overview,
    build_team_goal_usage,
    resolve_explicit_team_command,
)
from backend.modules.channels.base import InboundMessage, OutboundMessage
from backend.modules.config.loader import config_loader
from backend.modules.external_agents.conversation import (
    build_history_prompt,
    resolve_effective_session_mode,
)
from backend.modules.external_agents.routing import (
    extract_explicit_external_agent_request,
)
from backend.modules.messaging.enterprise_queue import EnterpriseMessageQueue
from backend.modules.messaging.rate_limiter import RateLimiter
from backend.modules.providers.runtime import (
    build_provider_unavailable_message,
    get_provider_runtime_state,
)
from backend.modules.session import (
    build_session_model_override,
    resolve_session_runtime_config,
)
from backend.modules.session.message_context import normalize_assistant_persistence_payload
from backend.modules.tools.setup import register_all_tools

# 预编译 @mention 清理正则
# 飞书格式: @_user_数字 (如 @_user_1)
# 企业微信/钉钉格式: <at user_id="xxx">@用户名</at>
_AT_MENTION_RE = re.compile(r"@_user_\d+\s*|<at[^>]*>.*?</at>\s*", re.IGNORECASE)
# 纯文本唤醒 mention（例如企业微信/钉钉客户端展开后的 "@SBot "）
# 仅移除消息开头连续的 mention 前缀，避免把正文中的 @账号 / 邮箱误删。
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

    return {
        "channel": msg.channel,
        "is_group": is_group,
        "group_chat_id": group_chat_id,
        "session_chat_id": group_chat_id if is_group else _safe_text(msg.chat_id),
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


def _normalize_assistant_output(
    content: Optional[str],
    reasoning_content: Optional[str] = None,
) -> tuple[str, str]:
    normalized_content, normalized_reasoning, _ = normalize_assistant_persistence_payload(
        content,
        reasoning_content,
    )
    return normalized_content, str(normalized_reasoning or "")


class ChannelMessageHandler:
    """频道消息处理器

    职责：
    - 从消息总线消费入站消息
    - 通过 Agent 循环生成回复
    - 将回复发布到出站总线
    - 管理会话和命令
    """

    def __init__(
        self,
        provider,  # LLMProvider
        workspace: Path,
        model: str,
        bus: EnterpriseMessageQueue,
        context_builder: ContextBuilder,
        tool_params: dict,
        subagent_manager=None,
        max_iterations: int = 10,
        rate_limiter: Optional[RateLimiter] = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        thinking_enabled: bool = True,
        max_history_messages: int = 50,
        memory_store=None,
    ):
        self.bus = bus
        self.rate_limiter = rate_limiter
        self._active_tasks: Dict[str, CancellationToken] = {}
        self._last_session_list_scope: Dict[str, str] = {}
        self._route_mode_overrides: Dict[str, str] = {}
        self._coder_profile_overrides: Dict[str, str] = {}
        self.db_session_factory = get_db_session_factory()
        self.channel_manager = None
        self.max_history_messages = max_history_messages

        self.context_builder = context_builder
        self._tool_params = dict(tool_params)
        self._subagent_manager = subagent_manager
        self._memory_store = memory_store

        self.tool_registry = register_all_tools(
            **self._tool_params, memory_store=memory_store
        )

        self.agent_loop = AgentLoop(
            provider=provider,
            workspace=workspace,
            tools=self.tool_registry,
            context_builder=self.context_builder,
            subagent_manager=subagent_manager,
            model=model,
            max_iterations=max_iterations,
            temperature=temperature,
            max_tokens=max_tokens,
            thinking_enabled=thinking_enabled,
        )

    def _rebuild_tool_registry(self) -> None:
        """按最新参数重建工具注册表。"""
        register_kwargs = dict(self._tool_params)
        if self.channel_manager is not None:
            register_kwargs["channel_manager"] = self.channel_manager

        self.tool_registry = register_all_tools(
            **register_kwargs,
            memory_store=self._memory_store,
        )
        self.agent_loop.tools = self.tool_registry

    # ------------------------------------------------------------------
    # 配置热重载
    # ------------------------------------------------------------------

    def reload_config(
        self,
        provider=None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        max_iterations: Optional[int] = None,
        thinking_enabled: Optional[bool] = None,
        max_history_messages: Optional[int] = None,
        persona_config=None,
        workspace=None,
        memory_store=None,
        tool_params_updates: Optional[dict] = None,
    ) -> None:
        """热重载 AI 配置（前端修改设置后调用）。"""
        should_rebuild_tools = False

        if provider is not None:
            self.agent_loop.provider = provider
        if model is not None:
            self.agent_loop.model = model
        if temperature is not None:
            self.agent_loop.temperature = temperature
        if max_tokens is not None:
            self.agent_loop.max_tokens = max_tokens
        if max_iterations is not None:
            self.agent_loop.max_iterations = max_iterations
        if thinking_enabled is not None:
            self.agent_loop.thinking_enabled = thinking_enabled
        if max_history_messages is not None:
            self.max_history_messages = max_history_messages

        if persona_config is not None:
            self.context_builder.persona_config = persona_config
            logger.info(
                f"Persona reloaded: ai_name={persona_config.ai_name}, "
                f"user_name={persona_config.user_name}, "
                f"user_address={getattr(persona_config, 'user_address', '')}"
            )

        if memory_store is not None:
            self._memory_store = memory_store
            self.context_builder.memory = memory_store
            should_rebuild_tools = True

        if tool_params_updates:
            self._tool_params.update(tool_params_updates)
            should_rebuild_tools = True

        if workspace is not None:
            self._tool_params["workspace"] = workspace
            self.agent_loop.workspace = workspace
            self.context_builder.workspace = workspace
            if self.agent_loop.subagent_manager:
                self.agent_loop.subagent_manager.workspace = workspace
            should_rebuild_tools = True
            logger.info(f"Workspace path reloaded: {workspace}")

        if should_rebuild_tools:
            self._rebuild_tool_registry()

        temp_label = "default" if temperature is None or temperature <= 0 else temperature
        max_tokens_label = "auto" if max_tokens is None or max_tokens <= 0 else max_tokens
        logger.info(
            f"Handler config reloaded: model={model}, temp={temp_label}, "
            f"max_tokens={max_tokens_label}"
        )

    def set_channel_manager(self, channel_manager) -> None:
        """设置频道管理器，重新注册工具以支持 send_media。"""
        self.channel_manager = channel_manager
        self._rebuild_tool_registry()

    # ------------------------------------------------------------------
    # 消息处理循环
    # ------------------------------------------------------------------

    async def start_processing(self) -> None:
        """从消息总线消费入站消息并分发处理。"""
        logger.info("Message processing loop started")
        consecutive_errors = 0
        max_consecutive_errors = 10

        while True:
            try:
                msg = await self.bus.consume_inbound()
                consecutive_errors = 0
                asyncio.create_task(self.handle_message(msg))
            except Exception as e:
                consecutive_errors += 1
                logger.error(
                    f"Processing loop error (consecutive: {consecutive_errors}): {e}"
                )
                if consecutive_errors >= max_consecutive_errors:
                    logger.critical(
                        f"Too many consecutive errors ({consecutive_errors}), restarting loop..."
                    )
                    consecutive_errors = 0
                    await asyncio.sleep(5)
                else:
                    await asyncio.sleep(1)

    async def handle_message(self, msg: InboundMessage) -> None:
        """处理单条入站消息：命令识别、Agent 处理、回复"""
        cancel_token = CancellationToken()
        session_id = None
        start_time = time.time()
        typing_session_key = None

        stream_handler = msg.metadata.get('_stream_handler') if msg.metadata else None
        stream_abort_handler = msg.metadata.get('_stream_abort_handler') if msg.metadata else None
        tool_event_handler = msg.metadata.get('_tool_event_handler') if msg.metadata else None

        try:
            logger.info(
                f"[{msg.channel}] Handling from {msg.sender_id} "
                f"(chat={msg.chat_id}): {msg.content[:50]}..."
            )

            content = _normalize_channel_inbound_content(msg)
            session_route = _resolve_session_route(msg)
            user_message_context = self._build_user_message_context(msg, session_route)
            model_input = _format_message_for_model("user", content, user_message_context)
            mentioned_team = None
            team_finder = getattr(self.context_builder, "_find_mentioned_team", None)
            if callable(team_finder):
                try:
                    mentioned_team = team_finder(content)
                except Exception as e:
                    logger.warning(f"[{msg.channel}] Failed to detect mentioned team: {e}")
            prefer_direct_workflow_result = bool(mentioned_team)
            typing_session_key = await self._maybe_start_channel_typing(msg)

            # 限流检查
            if self.rate_limiter:
                allowed, error_msg = await self.rate_limiter.check(msg.sender_id)
                if not allowed:
                    logger.warning(f"[{msg.channel}] Rate limit for {msg.sender_id}")
                    if stream_handler:
                        await stream_handler(error_msg, is_final=True)
                    else:
                        await self._send_reply(msg, error_msg)
                    return

            # 命令分发
            cmd = content.strip().lower()
            if cmd in ("/new", "/newsession", "/new_session", "/n"):
                await self._handle_new_session_command(msg)
                return
            if cmd in ("/list", "/sessions", "/list_sessions", "/l", "/ls"):
                await self._handle_list_sessions_command(msg)
                return
            if cmd in ("/all", "/all_sessions", "/al"):
                await self._handle_list_sessions_command(msg, include_all=True)
                return
            if cmd.startswith(("/switch ", "/切换 ", "/s ")):
                await self._handle_switch_session_command(msg, content)
                return
            if cmd in ("/clear", "/clear_history", "/c"):
                await self._handle_clear_history_command(msg)
                return
            if cmd in ("/stop", "/cancel"):
                await self._handle_stop_command(msg)
                return
            if cmd in ("/help", "/h", "/?"):
                await self._handle_help_command(msg)
                return
            if cmd.startswith(("/route", "/rt")):
                await self._handle_route_command(msg, content)
                return
            if cmd.startswith(("/coder", "/cdr")):
                await self._handle_coder_command(msg, content)
                return
            if cmd == "/team" or cmd.startswith("/team "):
                await self._handle_team_command(
                    msg,
                    content,
                    session_route=session_route,
                    user_message_context=user_message_context,
                    cancel_token=cancel_token,
                    tool_event_handler=tool_event_handler,
                    start_time=start_time,
                )
                return
            if cmd.startswith(("/provider ", "/提供商 ", "/m ")) or cmd in ("/provider", "/提供商", "/m"):
                await self._handle_provider_command(msg, content)
                return
            if cmd.startswith(("/personality ", "/性格 ", "/p ")) or cmd in ("/personality", "/性格", "/p"):
                await self._handle_personality_command(msg, content)
                return

            if not content and not msg.media:
                logger.info(
                    f"[{msg.channel}] Ignoring empty inbound content after wakeup normalization "
                    f"(chat={msg.chat_id})"
                )
                return

            explicit_profile, explicit_task = self._resolve_explicit_external_coder(content)
            if explicit_profile and explicit_task:
                await self._handle_direct_coding_message(
                    msg=msg,
                    content=content,
                    task_content=explicit_task,
                    session_route=session_route,
                    user_message_context=user_message_context,
                    cancel_token=cancel_token,
                    coder_profile=explicit_profile,
                    start_time=start_time,
                )
                return

            route_mode, coder_profile = self._get_routing_preferences(msg)
            if route_mode == "direct":
                await self._handle_direct_coding_message(
                    msg=msg,
                    content=content,
                    session_route=session_route,
                    user_message_context=user_message_context,
                    cancel_token=cancel_token,
                    coder_profile=coder_profile,
                    start_time=start_time,
                )
                return

            # Agent 处理
            session_id = await self._get_or_create_session(msg)
            self._active_tasks[session_id] = cancel_token
            if stream_abort_handler:
                self._register_stream_abort_callback(
                    cancel_token,
                    stream_abort_handler,
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                )
            self.tool_registry.set_message_context(
                {
                    "channel": msg.channel,
                    "sender_id": msg.sender_id,
                    "chat_id": msg.chat_id,
                    "metadata": msg.metadata,
                }
            )

            if cancel_token.is_cancelled:
                return

            self.tool_registry.set_session_id(session_id)
            workflow_tool = self.tool_registry.get_tool("workflow_run")
            if workflow_tool and hasattr(workflow_tool, "set_event_callback"):
                workflow_tool.set_event_callback(tool_event_handler)
            await self._save_message(
                session_id,
                "user",
                content,
                message_context=user_message_context,
            )

            runtime_config = await self._resolve_runtime_config_for_session(session_id)
            _validate_runtime_provider(runtime_config)
            model_override = build_session_model_override(runtime_config, force=True)
            persona_override = runtime_config.persona_config
            active_provider, _, _, _, _, _ = self.agent_loop._resolve_execution_runtime(
                model_override
            )
            history = await self._get_session_history(
                session_id,
                max_history_messages=runtime_config.persona_config.max_history_messages,
                summary_provider=active_provider,
            )
            if history and history[-1].get("role") == "user":
                history = history[:-1]

            if runtime_config.use_custom_config:
                if runtime_config.has_custom_model_config:
                    logger.info(
                        f"[{msg.channel}] ✓ 使用会话级模型配置: "
                        f"{runtime_config.provider_name}/{runtime_config.model_name}"
                    )
                if runtime_config.has_custom_persona_config:
                    logger.info(
                        f"[{msg.channel}] ✓ 使用自定义性格: "
                        f"{runtime_config.persona_config.personality}"
                    )
            else:
                logger.info(
                    f"[{msg.channel}] 使用全局配置: "
                    f"{runtime_config.provider_name}/{runtime_config.model_name}"
                )

            # 流式模式：实时发送每个 chunk
            response_reasoning = ""
            if stream_handler:
                response_parts = []
                reasoning_parts = []

                async def reasoning_event_handler(reasoning_chunk: str) -> None:
                    if not reasoning_chunk:
                        return
                    reasoning_parts.append(reasoning_chunk)
                    await stream_handler(
                        reasoning_chunk,
                        is_final=False,
                        is_reasoning=True,
                    )

                async for chunk in self.agent_loop.process_message(
                    message=model_input,
                    session_id=session_id,
                    context=history,
                    media=msg.media,
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    account_id=str((msg.metadata or {}).get("account_id") or "").strip() or None,
                    cancel_token=cancel_token,
                    yield_intermediate=True,
                    model_override=model_override,
                    persona_override=persona_override,
                    tool_event_handler=tool_event_handler,
                    reasoning_event_handler=reasoning_event_handler,
                    prefer_direct_workflow_result=prefer_direct_workflow_result,
                ):
                    if cancel_token.is_cancelled:
                        break
                    response_parts.append(chunk)
                    await stream_handler(chunk, is_final=False)

                response, response_reasoning = _normalize_assistant_output(
                    "".join(response_parts),
                    "".join(reasoning_parts),
                )
                if not response and response_reasoning:
                    response = "抱歉，这次没有整理出可发送的回复，请重试。"
                if not cancel_token.is_cancelled:
                    await stream_handler("", is_final=True)
            else:
                # 传统模式：收集所有响应后再发送
                response, response_reasoning = await self._process_with_agent(
                    session_id, model_input, history, cancel_token,
                    media=msg.media,
                    channel=msg.channel, chat_id=msg.chat_id,
                    account_id=str((msg.metadata or {}).get("account_id") or "").strip() or None,
                    runtime_config=runtime_config,
                    tool_event_handler=tool_event_handler,
                    prefer_direct_workflow_result=prefer_direct_workflow_result,
                )

            if cancel_token.is_cancelled:
                logger.info(f"[{msg.channel}] Task cancelled for session {session_id}")
                if stream_handler and not stream_abort_handler:
                    await stream_handler("Task cancelled", is_final=True)
                elif not stream_handler:
                    await self._send_reply(msg, "Task cancelled")
                return

            if response:
                assistant_message_context = _encode_message_context(
                    {
                        **self._build_assistant_message_context(msg, session_route),
                        **({"reasoning_content": response_reasoning} if response_reasoning else {}),
                    }
                )
                # 保存消息到数据库
                async with self.db_session_factory() as db:
                    from backend.modules.session.manager import SessionManager
                    session_manager = SessionManager(db)
                    
                    assistant_message = await session_manager.add_message(
                        session_id=session_id,
                        role="assistant",
                        content=response,
                        message_context=assistant_message_context,
                    )
                    
                    # 回填 message_id 到工具调用记录
                    try:
                        from backend.modules.tools.conversation_history import get_conversation_history
                        conversation_history = get_conversation_history()
                        updated_count = await conversation_history.backfill_message_id(
                            session_id=session_id,
                            message_id=assistant_message.id,
                        )
                        if updated_count > 0:
                            logger.info(
                                f"[{msg.channel}] Backfilled message_id={assistant_message.id} "
                                f"to {updated_count} tool conversations"
                            )
                    except Exception as e:
                        logger.warning(f"[{msg.channel}] Failed to backfill message_id: {e}")

                try:
                    mirrored_session_id = await self._mirror_group_exchange_to_primary_context(
                        msg=msg,
                        user_content=content,
                        assistant_content=response,
                        session_route=session_route,
                    )
                    if mirrored_session_id:
                        logger.info(
                            f"[{msg.channel}] Mirrored group exchange to primary session "
                            f"{mirrored_session_id} from account={session_route['source_account_id']}"
                        )
                except Exception as e:
                    logger.warning(f"[{msg.channel}] Failed to mirror group exchange: {e}")
                
                # 剥离工作流元数据注释
                channel_response = _WORKFLOW_META_RE.sub("", response).strip()
                
                # 非流式模式才需要发送回复
                if not stream_handler:
                    await self._send_reply(msg, channel_response or response)
                
                duration = time.time() - start_time
                logger.info(f"[{msg.channel}] Handled session {session_id} in {duration:.2f}s")
            else:
                logger.warning(f"[{msg.channel}] No response for session {session_id}")

        except Exception as e:
            duration = time.time() - start_time
            logger.exception(f"[{msg.channel}] Error after {duration:.2f}s: {e}")
            
            if stream_handler:
                try:
                    await stream_handler(_friendly_channel_error(str(e)), is_final=True)
                except Exception as se:
                    logger.error(f"[{msg.channel}] Failed to send error via stream_handler: {se}")
            else:
                await self._send_reply(msg, _friendly_channel_error(str(e)))

        finally:
            await self._maybe_stop_channel_typing(msg, typing_session_key)
            workflow_tool = self.tool_registry.get_tool("workflow_run")
            if workflow_tool and hasattr(workflow_tool, "set_event_callback"):
                workflow_tool.set_event_callback(None)
            self.tool_registry.set_message_context(None)
            if session_id and session_id in self._active_tasks:
                del self._active_tasks[session_id]

    async def _maybe_start_channel_typing(self, msg: InboundMessage) -> Optional[str]:
        """按渠道能力开启 typing 提示。"""
        if msg.channel != "wechat" or self.channel_manager is None:
            return None

        metadata = msg.metadata or {}
        account_id = str(metadata.get("account_id") or "default").strip() or "default"
        context_token = str(metadata.get("context_token") or "").strip()
        if not context_token:
            return None

        channel = self.channel_manager.get_channel("wechat", account_id=account_id)
        if channel is None or not hasattr(channel, "open_typing_session"):
            return None

        try:
            return await channel.open_typing_session(
                chat_id=str(msg.chat_id),
                context_token=context_token,
            )
        except Exception as e:
            logger.debug(f"[wechat] Failed to start typing session: {e}")
            return None

    async def _maybe_stop_channel_typing(
        self,
        msg: InboundMessage,
        typing_session_key: Optional[str],
    ) -> None:
        """关闭渠道 typing 提示。"""
        if msg.channel != "wechat" or not typing_session_key or self.channel_manager is None:
            return

        metadata = msg.metadata or {}
        account_id = str(metadata.get("account_id") or "default").strip() or "default"
        channel = self.channel_manager.get_channel("wechat", account_id=account_id)
        if channel is None or not hasattr(channel, "close_typing_session"):
            return

        try:
            await channel.close_typing_session(typing_session_key)
        except Exception as e:
            logger.debug(f"[wechat] Failed to stop typing session: {e}")

    def _register_stream_abort_callback(
        self,
        cancel_token: CancellationToken,
        abort_handler,
        *,
        channel: str,
        chat_id: str,
    ) -> None:
        """将任务取消与渠道侧流式卡片终止联动。"""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        def _schedule_abort() -> None:
            logger.info(f"[{channel}] Triggering stream abort callback (chat={chat_id})")
            loop.create_task(abort_handler())

        cancel_token.register_callback(_schedule_abort)

    # ------------------------------------------------------------------
    # Agent 处理
    # ------------------------------------------------------------------

    async def _resolve_runtime_config_for_session(self, session_id: str):
        """解析指定会话当前消息应使用的运行时配置。"""
        async with self.db_session_factory() as db:
            from sqlalchemy import select

            result = await db.execute(select(Session).where(Session.id == session_id))
            session = result.scalar_one_or_none()

        return resolve_session_runtime_config(config_loader.config, session)

    async def _process_with_agent(
        self,
        session_id: str,
        user_message: str,
        history: List[dict],
        cancel_token: CancellationToken,
        media: Optional[List[str]] = None,
        channel: Optional[str] = None,
        chat_id: Optional[str] = None,
        account_id: Optional[str] = None,
        runtime_config=None,
        tool_event_handler=None,
        prefer_direct_workflow_result: bool = False,
    ) -> tuple[str, str]:
        """运行 Agent 循环并收集响应。"""
        try:
            if runtime_config is None:
                runtime_config = await self._resolve_runtime_config_for_session(session_id)

            _validate_runtime_provider(runtime_config)
            model_override = build_session_model_override(runtime_config, force=True)
            persona_override = runtime_config.persona_config

            parts = []
            reasoning_parts = []

            async def reasoning_event_handler(reasoning_chunk: str) -> None:
                if reasoning_chunk:
                    reasoning_parts.append(reasoning_chunk)

            async for chunk in self.agent_loop.process_message(
                message=user_message,
                session_id=session_id,
                context=history,
                media=media,
                channel=channel,
                chat_id=chat_id,
                account_id=account_id,
                cancel_token=cancel_token,
                yield_intermediate=True,  # 启用流式输出
                model_override=model_override,
                persona_override=persona_override,
                tool_event_handler=tool_event_handler,
                reasoning_event_handler=reasoning_event_handler,
                prefer_direct_workflow_result=prefer_direct_workflow_result,
            ):
                if cancel_token.is_cancelled:
                    break
                parts.append(chunk)
            result, normalized_reasoning = _normalize_assistant_output(
                "".join(parts),
                "".join(reasoning_parts),
            )
            return (
                result
                or (
                    "抱歉，这次没有整理出可发送的回复，请重试。"
                    if normalized_reasoning
                    else "抱歉，未能生成回复，请稍后重试。"
                ),
                normalized_reasoning,
            )
        except Exception as e:
            logger.error(f"Agent processing error: {e}")
            return _friendly_channel_error(str(e)), ""

    # ------------------------------------------------------------------
    # 回复
    # ------------------------------------------------------------------

    async def _send_reply(self, original_msg: InboundMessage, content: str) -> None:
        """发布回复到出站总线。"""
        try:
            reply = OutboundMessage(
                channel=original_msg.channel,
                chat_id=original_msg.chat_id,
                content=content,
                metadata=original_msg.metadata,  # 传递原始消息的 metadata
            )
            await self.bus.publish_outbound(reply)
        except Exception as e:
            logger.error(f"[{original_msg.channel}] Failed to queue reply: {e}")

    # ------------------------------------------------------------------
    # 会话管理命令
    # ------------------------------------------------------------------

    def _get_chat_key(self, msg: InboundMessage) -> str:
        """返回频道内唯一聊天键。"""
        session_route = _resolve_session_route(msg)
        return (
            f"{msg.channel}:"
            f"{session_route['context_owner_account_id']}:"
            f"{session_route['session_chat_id']}"
        )

    def _remember_session_list_scope(self, msg: InboundMessage, include_all: bool) -> None:
        """记录当前聊天最近一次使用的列表范围。"""
        self._last_session_list_scope[self._get_chat_key(msg)] = "all" if include_all else "chat"

    def _get_last_session_list_scope(self, msg: InboundMessage) -> str:
        """获取当前聊天最近一次使用的列表范围，默认当前聊天。"""
        return getattr(self, "_last_session_list_scope", {}).get(self._get_chat_key(msg), "chat")

    async def _load_recent_sessions(
        self, msg: InboundMessage, include_all: bool = False, limit: int = 10
    ) -> List[Session]:
        """加载最近会话列表。"""
        from sqlalchemy import select

        query = select(Session)
        if not include_all:
            session_route = _resolve_session_route(msg)
            account_id = str(session_route["context_owner_account_id"])
            session_chat_id = str(session_route["session_chat_id"])
            prefix = f"{msg.channel}:{account_id}:{session_chat_id}"
            if account_id == _PRIMARY_ACCOUNT_ID:
                legacy_prefix = f"{msg.channel}:{session_chat_id}"
                query = query.where(
                    (Session.name.like(f"{prefix}%")) | (Session.name.like(f"{legacy_prefix}%"))
                )
            else:
                query = query.where(Session.name.like(f"{prefix}%"))

        query = query.order_by(Session.updated_at.desc()).limit(limit)

        async with self.db_session_factory() as db:
            result = await db.execute(query)
            return list(result.scalars().all())

    async def _load_session_message_counts(self, session_ids: List[str]) -> Dict[str, int]:
        """批量加载会话消息数量。"""
        from sqlalchemy import func, select

        if not session_ids:
            return {}

        async with self.db_session_factory() as db:
            result = await db.execute(
                select(Message.session_id, func.count(Message.id))
                .where(Message.session_id.in_(session_ids))
                .group_by(Message.session_id)
            )
            return {session_id: count for session_id, count in result.all()}

    async def _get_session_by_id(self, session_id: str) -> Optional[Session]:
        """根据 ID 查找会话。"""
        from sqlalchemy import select

        async with self.db_session_factory() as db:
            result = await db.execute(select(Session).where(Session.id == session_id))
            return result.scalar_one_or_none()

    async def _get_or_create_session(self, msg: InboundMessage) -> str:
        """获取已有会话或创建新会话。"""
        if msg.metadata:
            existing_session_id = str(msg.metadata.get("session_id") or "").strip()
            if existing_session_id:
                return existing_session_id

        if hasattr(self, "_active_sessions"):
            chat_key = self._get_chat_key(msg)
            if chat_key in self._active_sessions:
                return self._active_sessions[chat_key]

        session_route = _resolve_session_route(msg)
        return await self._get_or_create_session_for_route(
            msg,
            session_route,
            cache_key=self._get_chat_key(msg),
        )

    async def _get_or_create_session_for_route(
        self,
        msg: InboundMessage,
        session_route: Dict[str, object],
        *,
        cache_key: Optional[str] = None,
    ) -> str:
        """按指定路由解析或创建会话。"""
        from sqlalchemy import select
        from datetime import datetime

        account_id = str(session_route["context_owner_account_id"])
        session_chat_id = str(session_route["session_chat_id"])
        prefix = f"{msg.channel}:{account_id}:{session_chat_id}"
        legacy_prefix = f"{msg.channel}:{session_chat_id}"
        channel_context = self._build_session_channel_context(msg, session_route)
        async with self.db_session_factory() as db:
            result = await db.execute(
                select(Session)
                .where(Session.name.like(f"{prefix}%"))
                .order_by(Session.created_at.desc())
                .limit(1)
            )
            session = result.scalar_one_or_none()
            if not session and account_id == "default":
                result = await db.execute(
                    select(Session)
                    .where(Session.name.like(f"{legacy_prefix}%"))
                    .order_by(Session.created_at.desc())
                    .limit(1)
                )
                session = result.scalar_one_or_none()
            if session:
                existing_context = _decode_message_context(getattr(session, "channel_context", None))
                if channel_context and channel_context != existing_context:
                    session.channel_context = json.dumps(channel_context, ensure_ascii=False)
                    await db.commit()
                return session.id

            # 创建新会话，使用带时间戳的名称
            import uuid
            session_name = (
                f"{msg.channel}:{account_id}:{session_chat_id}:"
                f"{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            )
            session = Session(
                id=str(uuid.uuid4()),
                name=session_name,
                channel_context=(
                    json.dumps(channel_context, ensure_ascii=False)
                    if channel_context
                    else None
                ),
                )
            db.add(session)
            await db.commit()
            await db.refresh(session)
            if cache_key:
                if not hasattr(self, "_active_sessions"):
                    self._active_sessions = {}
                self._active_sessions[cache_key] = session.id
            logger.info(f"Created session {session.id} for {session_name}")
            return session.id

    def _should_mirror_to_primary_context(self, session_route: Dict[str, object]) -> bool:
        """仅在支持的群聊渠道中，把非主机器人对话镜像到主机器人主群会话。"""
        return bool(
            session_route.get("supports_primary_group_shared")
            and session_route.get("is_group")
            and str(session_route.get("source_account_id") or "") != _PRIMARY_ACCOUNT_ID
        )

    def _build_primary_group_session_route(
        self,
        session_route: Dict[str, object],
    ) -> Dict[str, object]:
        """构造主机器人群共享会话路由，不改变原始回复账号。"""
        primary_route = dict(session_route)
        primary_route.update(
            {
                "context_owner_account_id": _PRIMARY_ACCOUNT_ID,
                "primary_account_id": _PRIMARY_ACCOUNT_ID,
                "session_scope": "group_shared_primary",
                "use_primary_group_context": True,
                "context_owner_bot_label": _format_bot_label(_PRIMARY_ACCOUNT_ID),
            }
        )
        return primary_route

    async def _mirror_group_exchange_to_primary_context(
        self,
        *,
        msg: InboundMessage,
        user_content: str,
        assistant_content: str,
        session_route: Dict[str, object],
    ) -> Optional[str]:
        """把非主机器人在群里的问答镜像写入主机器人群共享会话。"""
        if not self._should_mirror_to_primary_context(session_route):
            return None

        primary_route = self._build_primary_group_session_route(session_route)
        primary_cache_key = (
            f"{msg.channel}:{primary_route['context_owner_account_id']}:"
            f"{primary_route['session_chat_id']}"
        )
        primary_session_id = await self._get_or_create_session_for_route(
            msg,
            primary_route,
            cache_key=primary_cache_key,
        )

        async with self.db_session_factory() as db:
            from backend.modules.session.manager import SessionManager

            session_manager = SessionManager(db)
            await session_manager.add_message(
                session_id=primary_session_id,
                role="user",
                content=user_content,
                message_context=_encode_message_context(
                    self._build_user_message_context(msg, primary_route)
                ),
            )
            await session_manager.add_message(
                session_id=primary_session_id,
                role="assistant",
                content=assistant_content,
                message_context=_encode_message_context(
                    self._build_assistant_message_context(msg, primary_route)
                ),
            )

        return primary_session_id

    @staticmethod
    def _build_session_channel_context(
        msg: InboundMessage,
        session_route: Optional[Dict[str, object]] = None,
    ) -> Optional[dict]:
        """构建可持久化的频道会话上下文。"""
        session_route = session_route or _resolve_session_route(msg)
        account_id = str(session_route["context_owner_account_id"])

        context = {
            "channel": msg.channel,
            "account_id": account_id,
            "sender_id": str(msg.sender_id or ""),
            "chat_id": str(session_route["session_chat_id"] or msg.chat_id or ""),
            "source_account_id": str(session_route["source_account_id"]),
            "reply_account_id": str(session_route["reply_account_id"]),
            "context_owner_account_id": str(session_route["context_owner_account_id"]),
            "primary_account_id": str(session_route["primary_account_id"]),
            "session_scope": str(session_route["session_scope"]),
            "supports_primary_group_shared": bool(session_route["supports_primary_group_shared"]),
        }

        context.update({
            "is_group": bool(session_route["is_group"]),
            "delivery_mode": "chat" if session_route["is_group"] else "user",
            "to_user": None if session_route["is_group"] else (str(msg.sender_id or "") or str(msg.chat_id or "")),
            "group_chat_id": (
                str(session_route["group_chat_id"])
                if session_route["is_group"]
                else None
            ),
        })
        return context

    async def _handle_new_session_command(self, msg: InboundMessage) -> None:
        """处理 /new 命令。"""
        import uuid
        from datetime import datetime

        session_route = _resolve_session_route(msg)
        session_name = (
            f"{msg.channel}:{str(session_route['context_owner_account_id'])}:{str(session_route['session_chat_id'])}:"
            f"{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        session_id = str(uuid.uuid4())

        async with self.db_session_factory() as db:
            channel_context = self._build_session_channel_context(msg, session_route)
            db.add(
                Session(
                    id=session_id,
                    name=session_name,
                    channel_context=(
                        json.dumps(channel_context, ensure_ascii=False)
                        if channel_context
                        else None
                    ),
                )
            )
            await db.commit()

        if not hasattr(self, "_active_sessions"):
            self._active_sessions = {}
        self._active_sessions[self._get_chat_key(msg)] = session_id

        await self._send_reply(
            msg, 
            f"新会话已创建\n\n"
            f"名称: {session_name}\n"
            f"ID: {session_id}\n\n"
            f"现在可以开始新对话了"
        )

    async def _handle_list_sessions_command(
        self, msg: InboundMessage, include_all: bool = False
    ) -> None:
        """处理 /list 和 /al 命令。"""
        sessions = await self._load_recent_sessions(msg, include_all=include_all, limit=10)
        self._remember_session_list_scope(msg, include_all)

        if not sessions:
            empty_text = (
                "暂无会话记录\n\n"
                "使用 /n 创建第一个会话"
                if include_all
                else "当前聊天暂无会话记录\n\n使用 /n 创建第一个会话\n使用 /al 查看所有会话"
            )
            await self._send_reply(msg, empty_text)
            return

        counts = await self._load_session_message_counts([s.id for s in sessions])
        title = "所有会话列表 (最近10个)" if include_all else "当前聊天会话列表 (最近10个)"
        lines = [f"{title}\n━━━━━━━━━━━━━━━━━━━━━━\n"]
        for i, s in enumerate(sessions, 1):
            updated_at = getattr(s, "updated_at", None) or s.created_at
            updated = updated_at.strftime("%Y-%m-%d %H:%M")
            lines.append(
                f"[{i}] {s.name}\n"
                f"    ID: {s.id}\n"
                f"    更新: {updated} | 消息: {counts.get(s.id, 0)}\n"
            )
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("使用 /s <编号|ID> 切换，如: /s 1")
        lines.append("使用 /l 查看当前聊天会话" if include_all else "使用 /al 查看所有会话")
        await self._send_reply(msg, "\n".join(lines))

    async def _handle_switch_session_command(
        self, msg: InboundMessage, content: str
    ) -> None:
        """处理 /switch 命令，支持数字编号或完整ID。"""
        parts = content.split(maxsplit=1)
        if len(parts) < 2:
            await self._send_reply(
                msg, 
                "参数错误\n\n"
                "用法: /s <编号|ID>\n\n"
                "先用 /l 查看当前聊天会话，或 /al 查看所有会话"
            )
            return

        identifier = parts[1].strip()
        last_scope = self._get_last_session_list_scope(msg)
        scope_label = "所有会话" if last_scope == "all" else "当前聊天会话"

        # 尝试作为数字编号解析
        session = None
        if identifier.isdigit():
            sessions = await self._load_recent_sessions(
                msg, include_all=(last_scope == "all"), limit=10
            )
            if not sessions:
                await self._send_reply(
                    msg,
                    "暂无会话记录\n\n"
                    "使用 /l 查看当前聊天会话，或 /al 查看所有会话"
                )
                return

            index = int(identifier) - 1
            if 0 <= index < len(sessions):
                session = sessions[index]
            else:
                await self._send_reply(
                    msg,
                    f"编号 {identifier} 不存在\n\n"
                    f"当前 {scope_label} 中有 {len(sessions)} 个会话\n"
                    f"使用 /l 或 /al 重新查看列表"
                )
                return
        else:
            # 作为完整ID查找
            session = await self._get_session_by_id(identifier)
        
        if not session:
            await self._send_reply(
                msg, 
                f"会话不存在: {identifier}\n\n"
                f"使用 /l 或 /al 查看可用会话"
            )
            return

        if not hasattr(self, "_active_sessions"):
            self._active_sessions = {}
        self._active_sessions[self._get_chat_key(msg)] = session.id
        source_line = f"来源: {scope_label}\n" if identifier.isdigit() else ""
        await self._send_reply(
            msg, 
            f"已切换会话\n\n"
            f"{session.name}\n"
            f"ID: {session.id}\n"
            f"{source_line}\n"
            f"后续消息将继续写入这个会话"
        )

    async def _handle_clear_history_command(self, msg: InboundMessage) -> None:
        """处理 /clear 命令。"""
        from sqlalchemy import delete

        session_id = await self._get_or_create_session(msg)
        async with self.db_session_factory() as db:
            result = await db.execute(
                delete(Message).where(Message.session_id == session_id)
            )
            deleted_count = result.rowcount
            await db.commit()
        
        await self._send_reply(
            msg, 
            f"历史记录已清除\n\n"
            f"已删除 {deleted_count} 条消息"
        )

    async def _handle_stop_command(self, msg: InboundMessage) -> None:
        """处理 /stop 命令。"""
        session_id = await self._get_or_create_session(msg)
        if await self.cancel_task(session_id):
            await self._send_reply(msg, "任务已停止")
        else:
            await self._send_reply(msg, "没有正在执行的任务")

    async def _handle_personality_command(self, msg: InboundMessage, content: str) -> None:
        """处理 /personality 或 /p 命令 - 为当前会话设置性格。"""
        from backend.modules.agent.personalities import PERSONALITY_PRESETS
        from backend.modules.session.runtime_config import resolve_session_runtime_config
        from sqlalchemy import select
        import json
        
        session_id = await self._get_or_create_session(msg)
        parts = content.split(maxsplit=1)
        
        async with self.db_session_factory() as db:
            result = await db.execute(select(Session).where(Session.id == session_id))
            session = result.scalar_one_or_none()
            
            if not session:
                await self._send_reply(msg, "会话不存在")
                return
            
            runtime_config = resolve_session_runtime_config(config_loader.config, session)
            current_personality = runtime_config.persona_config.personality
            
            if len(parts) < 2:
                lines = ["可用性格列表\n━━━━━━━━━━━━━━━━━━━━━━\n"]
                
                personality_list = list(PERSONALITY_PRESETS.items())
                for i, (pid, preset) in enumerate(personality_list, 1):
                    marker = " [当前]" if pid == current_personality else ""
                    lines.append(f"[{i}] {pid} - {preset['name']}{marker}")
                
                lines.append("\n━━━━━━━━━━━━━━━━━━━━━━")
                lines.append(f"当前会话性格: {current_personality}")
                lines.append("\n使用 /p <编号|性格ID> 切换")
                lines.append("如: /p 1 或 /p friendly")
                await self._send_reply(msg, "\n".join(lines))
                return
            
            identifier = parts[1].strip().lower()
            personality_id = None
            
            personality_list = list(PERSONALITY_PRESETS.items())
            if identifier.isdigit():
                index = int(identifier) - 1
                if 0 <= index < len(personality_list):
                    personality_id = personality_list[index][0]
                else:
                    await self._send_reply(
                        msg,
                        f"编号 {identifier} 不存在\n\n"
                        f"当前有 {len(personality_list)} 个性格\n"
                        f"使用 /p 查看列表"
                    )
                    return
            else:
                if identifier in PERSONALITY_PRESETS:
                    personality_id = identifier
            
            if not personality_id:
                await self._send_reply(
                    msg,
                    f"性格 '{identifier}' 不存在\n\n"
                    f"使用 /p 查看可用性格"
                )
                return
            
            persona_config = {
                "ai_name": config_loader.config.persona.ai_name or "小C",
                "user_name": config_loader.config.persona.user_name or "用户",
                "user_address": getattr(config_loader.config.persona, 'user_address', '') or "",
                "personality": personality_id,
                "custom_personality": "",
            }
            
            session.session_persona_config = json.dumps(persona_config, ensure_ascii=False)
            session.use_custom_config = True
            await db.commit()
            
            preset = PERSONALITY_PRESETS[personality_id]
            await self._send_reply(
                msg,
                f"当前会话性格已设置为: {preset['name']}\n\n"
                f"{preset['description']}\n\n"
                f"此设置仅对当前会话生效"
            )

    async def _handle_provider_command(self, msg: InboundMessage, content: str) -> None:
        """处理 /provider 或 /m 命令 - 为当前会话设置模型提供商。
        
        用法:
        - /m                    查看可用提供商列表
        - /m 1                  使用编号切换（使用提供商默认模型）
        - /m 1 gpt-4           使用编号切换并指定模型名称
        - /m openai            使用ID切换（使用提供商默认模型）
        - /m openai gpt-4      使用ID切换并指定模型名称
        """
        from backend.modules.providers.registry import get_provider_metadata
        from backend.modules.providers.runtime import get_provider_runtime_state
        from backend.modules.config.loader import config_loader
        from backend.modules.session.runtime_config import resolve_session_runtime_config
        from sqlalchemy import select
        import json
        
        session_id = await self._get_or_create_session(msg)
        parts = content.split(maxsplit=2)
        
        async with self.db_session_factory() as db:
            result = await db.execute(select(Session).where(Session.id == session_id))
            session = result.scalar_one_or_none()
            
            if not session:
                await self._send_reply(msg, "会话不存在")
                return
            
            runtime_config = resolve_session_runtime_config(config_loader.config, session)
            current_provider = runtime_config.provider_name
            current_model = runtime_config.model_name
            is_custom_config = runtime_config.has_custom_model_config
            
            if len(parts) < 2:
                lines = ["已配置的模型提供商\n━━━━━━━━━━━━━━━━━━━━━━\n"]
                
                available_providers = []
                for provider_id, provider_config in config_loader.config.providers.items():
                    metadata = get_provider_metadata(provider_id)
                    runtime_state = get_provider_runtime_state(config_loader.config, provider_id)
                    if metadata and runtime_state.selectable:
                        available_providers.append((provider_id, metadata, provider_config))
                
                if not available_providers:
                    await self._send_reply(
                        msg,
                        "暂无已配置的提供商\n\n"
                        "请在 Web 界面配置 API Key"
                    )
                    return
                
                for i, (provider_id, metadata, provider_config) in enumerate(available_providers, 1):
                    is_current = provider_id == current_provider
                    marker = " ✓" if is_current else ""
                    lines.append(f"[{i}] {provider_id} - {metadata.name}{marker}")
                    
                    default_model = provider_config.model or metadata.default_model
                    if default_model:
                        lines.append(f"    默认: {default_model}")
                    
                    if is_current and current_model and current_model != default_model:
                        lines.append(f"    当前: {current_model} (自定义)")
                
                lines.append("\n━━━━━━━━━━━━━━━━━━━━━━")
                lines.append("当前会话配置:")
                if current_provider and current_model:
                    config_type = "自定义配置" if is_custom_config else "全局配置"
                    lines.append(f"  提供商: {current_provider}")
                    lines.append(f"  模型: {current_model}")
                    lines.append(f"  类型: {config_type}")
                else:
                    lines.append("  未配置")
                lines.append("\n使用方式:")
                lines.append("  /m <编号|ID>              使用默认模型")
                lines.append("  /m <编号|ID> <模型名>     指定模型名称")
                lines.append("\n示例:")
                lines.append("  /m 1                      使用第1个提供商的默认模型")
                lines.append("  /m 1 gpt-4               使用第1个提供商的 gpt-4")
                lines.append("  /m openai gpt-3.5-turbo  使用 openai 的 gpt-3.5-turbo")
                await self._send_reply(msg, "\n".join(lines))
                return
            
            identifier = parts[1].strip().lower()
            custom_model = parts[2].strip() if len(parts) > 2 else None
            
            available_providers = []
            for provider_id, provider_config in config_loader.config.providers.items():
                metadata = get_provider_metadata(provider_id)
                runtime_state = get_provider_runtime_state(config_loader.config, provider_id)
                if metadata and runtime_state.selectable:
                    available_providers.append((provider_id, metadata, provider_config))
            
            provider_id = None
            metadata = None
            provider_config = None
            
            if identifier.isdigit():
                index = int(identifier) - 1
                if 0 <= index < len(available_providers):
                    provider_id, metadata, provider_config = available_providers[index]
                else:
                    await self._send_reply(
                        msg,
                        f"编号 {identifier} 不存在\n\n"
                        f"当前有 {len(available_providers)} 个提供商\n"
                        f"使用 /m 查看列表"
                    )
                    return
            else:
                metadata = get_provider_metadata(identifier)
                if metadata:
                    provider_config = config_loader.config.providers.get(identifier)
                    if provider_config and get_provider_runtime_state(config_loader.config, identifier).selectable:
                        provider_id = identifier
            
            if not provider_id or not metadata or not provider_config:
                await self._send_reply(
                    msg,
                    f"提供商 '{identifier}' 不存在或未配置\n\n"
                    f"使用 /m 查看可用提供商"
                )
                return
            
            model_name = custom_model if custom_model else (provider_config.model or metadata.default_model)
            
            if not model_name:
                await self._send_reply(
                    msg,
                    f"无法确定模型名称\n\n"
                    f"请指定模型名称:\n"
                    f"/m {identifier} <模型名>\n\n"
                    f"例如: /m {identifier} gpt-4"
                )
                return
            
            runtime_state = get_provider_runtime_state(config_loader.config, provider_id)
            api_key = runtime_state.api_key
            if runtime_state.requires_api_key and not api_key:
                await self._send_reply(
                    msg,
                    f"提供商 '{provider_id}' 缺少 API 密钥\n\n"
                    f"请在 Web 界面配置 API Key"
                )
                return
            
            api_base = runtime_state.api_base or metadata.default_api_base
            
            model_config = {
                "provider": provider_id,
                "model": model_name,
                "api_key": api_key,
                "api_base": api_base,
            }
            
            session.session_model_config = json.dumps(model_config, ensure_ascii=False)
            session.use_custom_config = True
            await db.commit()
            
            custom_note = " (自定义)" if custom_model else ""
            await self._send_reply(
                msg,
                f"当前会话模型已设置为:\n\n"
                f"提供商: {metadata.name}\n"
                f"模型: {model_name}{custom_note}\n\n"
                f"此设置仅对当前会话生效"
            )

    def _get_route_preference_key(self, msg: InboundMessage) -> str:
        return self._get_chat_key(msg)

    def _resolve_channel_account_config(self, msg: InboundMessage):
        channel_config = getattr(config_loader.config.channels, msg.channel, None)
        if channel_config is None:
            return None

        account_id = str((msg.metadata or {}).get("account_id") or "default")
        root_account_id = str(getattr(channel_config, "account_id", "default") or "default")
        if account_id == root_account_id:
            return channel_config

        account_cfg = getattr(channel_config, "accounts", {}).get(account_id)
        return account_cfg or channel_config

    def _get_routing_preferences(self, msg: InboundMessage) -> tuple[str, str]:
        key = self._get_route_preference_key(msg)
        channel_cfg = self._resolve_channel_account_config(msg)
        if channel_cfg is None:
            channel_cfg = object()

        route_mode = str(getattr(channel_cfg, "routing_mode", "ai") or "ai").strip().lower()
        if route_mode not in {"ai", "direct"}:
            route_mode = "ai"

        coder_profile = str(
            getattr(channel_cfg, "external_coding_profile", "") or ""
        ).strip()

        if key in self._route_mode_overrides:
            route_mode = self._route_mode_overrides[key]
        if key in self._coder_profile_overrides:
            coder_profile = self._coder_profile_overrides[key]

        return route_mode, coder_profile

    def _resolve_explicit_external_coder(self, content: str) -> tuple[str, str]:
        """Resolve explicit natural-language routing like '用 codex 帮我修一下'."""
        parsed = extract_explicit_external_agent_request(content)
        if not parsed:
            return "", ""

        requested_profile, task = parsed
        external_tool = self.tool_registry.get_tool("external_coding_agent")
        registry = getattr(external_tool, "registry", None)
        if registry is None:
            return "", ""

        try:
            canonical_name = registry.resolve_profile_name(requested_profile)
            registry.resolve_profile(canonical_name)
        except Exception:
            return "", ""

        return canonical_name, task

    def _prepare_external_task(
        self,
        profile,
        task: str,
        history: List[dict],
    ) -> str:
        """根据 profile 会话模式构造实际下发任务。"""
        session_mode = resolve_effective_session_mode(profile)
        if session_mode == "stateless":
            return task
        if session_mode == "native":
            return task
        return build_history_prompt(
            task=task,
            history_messages=history,
            history_message_count=profile.history_message_count,
        )

    async def _handle_route_command(self, msg: InboundMessage, content: str) -> None:
        """处理 /route 命令。"""
        parts = content.strip().split(maxsplit=1)
        current_mode, current_profile = self._get_routing_preferences(msg)

        if len(parts) == 1:
            await self._send_reply(
                msg,
                "当前聊天路由模式:\n\n"
                f"- 模式: {current_mode}\n"
                f"- 外部代理: {current_profile or '未设置'}\n\n"
                "用法:\n"
                "- /route ai\n"
                "- /route direct\n"
                "- /route default",
            )
            return

        value = parts[1].strip().lower()
        key = self._get_route_preference_key(msg)

        if value == "default":
            self._route_mode_overrides.pop(key, None)
            resolved_mode, resolved_profile = self._get_routing_preferences(msg)
            await self._send_reply(
                msg,
                "当前聊天已恢复为渠道默认路由设置。\n\n"
                f"- 模式: {resolved_mode}\n"
                f"- 外部代理: {resolved_profile or '未设置'}",
            )
            return

        if value not in {"ai", "direct"}:
            await self._send_reply(
                msg,
                "无效路由模式。\n\n"
                "可用值:\n"
                "- /route ai\n"
                "- /route direct\n"
                "- /route default",
            )
            return

        self._route_mode_overrides[key] = value
        await self._send_reply(
            msg,
            "当前聊天路由模式已更新。\n\n"
            f"- 模式: {value}\n"
            f"- 外部代理: {current_profile or '未设置'}",
        )

    async def _handle_coder_command(self, msg: InboundMessage, content: str) -> None:
        """处理 /coder 命令。"""
        parts = content.strip().split(maxsplit=1)
        current_mode, current_profile = self._get_routing_preferences(msg)
        external_tool = self.tool_registry.get_tool("external_coding_agent")
        registry = getattr(external_tool, "registry", None)
        enabled_profiles = registry.enabled_profile_names() if registry else []
        enabled_profiles_text = ", ".join(enabled_profiles) if enabled_profiles else "无"

        if len(parts) == 1:
            await self._send_reply(
                msg,
                "当前聊天外部编程代理设置:\n\n"
                f"- 当前模式: {current_mode}\n"
                f"- 当前代理: {current_profile or '未设置'}\n"
                f"- 已启用 profile: {enabled_profiles_text}\n\n"
                "用法:\n"
                "- /coder codex\n"
                "- /coder claude\n"
                "- /coder default",
            )
            return

        value = parts[1].strip()
        key = self._get_route_preference_key(msg)

        if value.lower() == "default":
            self._coder_profile_overrides.pop(key, None)
            resolved_mode, resolved_profile = self._get_routing_preferences(msg)
            await self._send_reply(
                msg,
                "当前聊天已恢复为渠道默认外部代理设置。\n\n"
                f"- 当前模式: {resolved_mode}\n"
                f"- 当前代理: {resolved_profile or '未设置'}",
            )
            return

        if registry is None:
            await self._send_reply(msg, "external_coding_agent 工具当前不可用。")
            return

        try:
            canonical_name = registry.resolve_profile_name(value)
            registry.resolve_profile(canonical_name)
        except Exception as e:
            await self._send_reply(
                msg,
                f"无法切换外部代理: {e}\n\n已启用 profile: {enabled_profiles_text}",
            )
            return

        self._coder_profile_overrides[key] = canonical_name
        await self._send_reply(
            msg,
            "当前聊天外部编程代理已更新。\n\n"
            f"- 当前模式: {current_mode}\n"
            f"- 当前代理: {canonical_name}",
        )

    async def _handle_direct_coding_message(
        self,
        *,
        msg: InboundMessage,
        content: str,
        task_content: Optional[str] = None,
        session_route: Dict[str, object],
        user_message_context: dict,
        cancel_token: CancellationToken,
        coder_profile: str,
        start_time: float,
    ) -> None:
        """在 direct 路由模式下直接调用 external_coding_agent。"""
        session_id = await self._get_or_create_session(msg)
        self._active_tasks[session_id] = cancel_token

        try:
            stream_abort_handler = msg.metadata.get('_stream_abort_handler') if msg.metadata else None
            if stream_abort_handler:
                self._register_stream_abort_callback(
                    cancel_token,
                    stream_abort_handler,
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                )

            self.tool_registry.set_message_context(
                {
                    "channel": msg.channel,
                    "sender_id": msg.sender_id,
                    "chat_id": msg.chat_id,
                    "metadata": msg.metadata,
                }
            )
            self.tool_registry.set_session_id(session_id)
            self.tool_registry.set_channel(msg.channel)
            self.tool_registry.set_cancel_token(cancel_token)

            await self._save_message(
                session_id,
                "user",
                content,
                message_context=user_message_context,
            )

            external_tool = self.tool_registry.get_tool("external_coding_agent")
            registry = getattr(external_tool, "registry", None)
            if registry is None:
                raise ValueError("external_coding_agent 工具当前不可用。")

            profile = registry.resolve_profile(coder_profile.strip() or None)
            history = await self._get_session_history(session_id)
            if history:
                history = history[:-1]
            prepared_task = self._prepare_external_task(
                profile,
                (task_content or content).strip(),
                history,
            )

            arguments = {
                "task": prepared_task,
                "mode": "run",
                "timeout": self._tool_params.get("command_timeout", 180),
                "profile": profile.name,
            }
            profile_name = profile.name

            result = await self.tool_registry.execute(
                tool_name="external_coding_agent",
                arguments=arguments,
            )

            if cancel_token.is_cancelled:
                logger.info(f"[{msg.channel}] Direct coding route cancelled for session {session_id}")
                await self._send_reply(msg, "Task cancelled")
                return

            async with self.db_session_factory() as db:
                from backend.modules.session.manager import SessionManager
                from backend.modules.tools.conversation_history import get_conversation_history

                session_manager = SessionManager(db)
                assistant_message = await session_manager.add_message(
                    session_id=session_id,
                    role="assistant",
                    content=result,
                    message_context=_encode_message_context(
                        self._build_assistant_message_context(msg, session_route)
                    ),
                )

                conversation_history = get_conversation_history()
                try:
                    await conversation_history.backfill_message_id(
                        session_id=session_id,
                        message_id=assistant_message.id,
                    )
                except Exception as e:
                    logger.warning(
                        f"[{msg.channel}] Failed to backfill direct-mode tool message_id: {e}"
                    )

            await self._send_reply(msg, result)
            duration = time.time() - start_time
            logger.info(
                f"[{msg.channel}] Direct coding route handled via profile={profile_name or 'auto'} "
                f"for session {session_id} in {duration:.2f}s"
            )
        finally:
            self.tool_registry.set_cancel_token(None)
            self._active_tasks.pop(session_id, None)

    async def _handle_help_command(self, msg: InboundMessage) -> None:
        """处理 /help 命令。"""
        help_text = (
            "可用命令\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "会话管理:\n"
            "  /new (/n) - 创建新会话\n"
            "  /list (/l) - 查看当前聊天最近10个会话\n"
            "  /all (/al) - 查看所有会话\n"
            "  /switch (/s) <编号|ID> - 切换最近一次列表中的会话\n"
            "  /clear (/c) - 清除当前会话历史\n\n"
            "个性化设置:\n"
            "  /personality (/p) [编号|ID] - 查看/切换性格\n"
            "  /provider (/m) [编号|ID] [模型] - 查看/切换模型\n\n"
            "渠道编程代理:\n"
            "  /route (/rt) [ai|direct|default] - 切换当前聊天路由模式\n"
            "  /coder (/cdr) [profile|default] - 切换当前聊天外部编程代理\n\n"
            "团队协作:\n"
            "  /team - 查看可用团队名称\n"
            "  /team <团队名> <任务> - 直接运行指定智能体团队\n\n"
            "控制:\n"
            "  /stop - 停止当前任务\n"
            "  /help (/h) - 显示此帮助\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "提示:\n"
            "- 直接发消息即可对话\n"
            "- 括号内为命令简写\n"
            "- /l 查看当前聊天，/al 查看所有会话\n"
            "- 使用 /m 或 /p 查看详细用法\n"
            "- /route direct 后，普通消息会直接转发给外部编程代理\n"
            "- /coder codex 可把当前聊天的直通代理切到 codex\n"
            "- 先发送 /team 可查看当前可用团队名称\n"
            "- /team 文档深度分析 请总结这份文档，可直接执行团队工作流\n"
            "- 也可以直接说“用 codex 帮我修这个报错”或“用 claude 写个爬虫”\n"
        )
        await self._send_reply(msg, help_text)

    async def _handle_team_command(
        self,
        msg: InboundMessage,
        content: str,
        *,
        session_route: Dict[str, object],
        user_message_context: dict,
        cancel_token: CancellationToken,
        tool_event_handler=None,
        start_time: Optional[float] = None,
    ) -> None:
        """处理渠道 /team 命令，直接执行指定团队工作流。"""
        if content.strip() == "/team":
            await self._send_reply(
                msg,
                build_team_command_overview(
                    self.context_builder,
                    log_scope="channel team command",
                ),
            )
            return

        resolved = resolve_explicit_team_command(
            self.context_builder,
            content,
            log_scope="channel team command",
        )
        if resolved is None:
            await self._send_reply(msg, "团队命令当前不可用，请稍后重试。")
            return

        team_name, goal = resolved
        if not team_name:
            await self._send_reply(
                msg,
                build_team_command_overview(
                    self.context_builder,
                    log_scope="channel team command",
                ),
            )
            return
        if not goal:
            await self._send_reply(msg, build_team_goal_usage(team_name))
            return

        session_id = await self._get_or_create_session(msg)
        self._active_tasks[session_id] = cancel_token
        self.tool_registry.set_message_context(
            {
                "channel": msg.channel,
                "sender_id": msg.sender_id,
                "chat_id": msg.chat_id,
                "metadata": msg.metadata,
            }
        )
        self.tool_registry.set_session_id(session_id)
        self.tool_registry.set_cancel_token(cancel_token)

        workflow_tool = self.tool_registry.get_tool("workflow_run")
        if workflow_tool and hasattr(workflow_tool, "set_event_callback"):
            workflow_tool.set_event_callback(tool_event_handler)

        try:
            await self._save_message(
                session_id,
                "user",
                content,
                message_context=user_message_context,
            )

            response = await self.tool_registry.execute(
                "workflow_run",
                {
                    "team_name": team_name,
                    "goal": goal,
                },
            )

            async with self.db_session_factory() as db:
                from backend.modules.session.manager import SessionManager

                session_manager = SessionManager(db)
                assistant_message = await session_manager.add_message(
                    session_id=session_id,
                    role="assistant",
                    content=response,
                    message_context=_encode_message_context(
                        self._build_assistant_message_context(msg, session_route)
                    ),
                )

                try:
                    from backend.modules.tools.conversation_history import get_conversation_history

                    conversation_history = get_conversation_history()
                    updated_count = await conversation_history.backfill_message_id(
                        session_id=session_id,
                        message_id=assistant_message.id,
                    )
                    if updated_count > 0:
                        logger.info(
                            f"[{msg.channel}] Backfilled message_id={assistant_message.id} "
                            f"to {updated_count} team command tool conversations"
                        )
                except Exception as e:
                    logger.warning(f"[{msg.channel}] Failed to backfill team command message_id: {e}")

            channel_response = _WORKFLOW_META_RE.sub("", response).strip()
            await self._send_reply(msg, channel_response or response)

            duration = time.time() - start_time if start_time is not None else 0.0
            logger.info(
                f"[{msg.channel}] Team command handled for session {session_id} "
                f"(team={team_name}) in {duration:.2f}s"
            )
        finally:
            if workflow_tool and hasattr(workflow_tool, "set_event_callback"):
                workflow_tool.set_event_callback(None)
            self.tool_registry.set_cancel_token(None)
            self.tool_registry.set_message_context(None)
            self._active_tasks.pop(session_id, None)

    # ------------------------------------------------------------------
    # 数据库辅助
    # ------------------------------------------------------------------

    def _build_user_message_context(
        self,
        msg: InboundMessage,
        session_route: Optional[Dict[str, object]] = None,
    ) -> dict:
        session_route = session_route or _resolve_session_route(msg)
        return {
            "channel": msg.channel,
            "role": "user",
            "sender_id": str(session_route["sender_id"]),
            "sender_name": str(session_route["sender_name"]),
            "source_account_id": str(session_route["source_account_id"]),
            "reply_account_id": str(session_route["reply_account_id"]),
            "context_owner_account_id": str(session_route["context_owner_account_id"]),
            "primary_account_id": str(session_route["primary_account_id"]),
            "session_scope": str(session_route["session_scope"]),
            "is_group": bool(session_route["is_group"]),
            "group_chat_id": (
                str(session_route["group_chat_id"])
                if session_route["is_group"]
                else None
            ),
            "target_bot_label": str(session_route["target_bot_label"]),
            "reply_bot_label": str(session_route["reply_bot_label"]),
        }

    def _build_assistant_message_context(
        self,
        msg: InboundMessage,
        session_route: Optional[Dict[str, object]] = None,
    ) -> dict:
        session_route = session_route or _resolve_session_route(msg)
        return {
            "channel": msg.channel,
            "role": "assistant",
            "source_account_id": str(session_route["source_account_id"]),
            "reply_account_id": str(session_route["reply_account_id"]),
            "context_owner_account_id": str(session_route["context_owner_account_id"]),
            "primary_account_id": str(session_route["primary_account_id"]),
            "session_scope": str(session_route["session_scope"]),
            "is_group": bool(session_route["is_group"]),
            "group_chat_id": (
                str(session_route["group_chat_id"])
                if session_route["is_group"]
                else None
            ),
            "reply_bot_label": str(session_route["reply_bot_label"]),
            "target_bot_label": str(session_route["target_bot_label"]),
        }

    async def _save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        message_context: Optional[dict] = None,
    ) -> None:
        """保存消息到数据库。"""
        async with self.db_session_factory() as db:
            db.add(
                Message(
                    session_id=session_id,
                    role=role,
                    content=content,
                    message_context=_encode_message_context(message_context),
                )
            )
            await db.commit()

    async def _get_session_history(
        self,
        session_id: str,
        *,
        max_history_messages: Optional[int] = None,
        summary_provider=None,
    ) -> List[dict]:
        """获取会话历史消息。"""
        from sqlalchemy import select

        if max_history_messages is None:
            max_history_messages = self.max_history_messages
        if summary_provider is None:
            summary_provider = self.agent_loop.provider

        limit = max_history_messages if max_history_messages != -1 else None

        async with self.db_session_factory() as db:
            if limit is not None:
                query = (
                    select(Message)
                    .where(Message.session_id == session_id)
                    .order_by(Message.created_at.desc())
                    .limit(limit)
                )
                result = await db.execute(query)
                messages = list(result.scalars().all())
                message_dicts = [
                    {
                        "role": m.role,
                        "content": _format_message_for_model(
                            m.role,
                            m.content,
                            _decode_message_context(getattr(m, "message_context", None)),
                        ),
                    }
                    for m in reversed(messages)
                ]
            else:
                query = (
                    select(Message)
                    .where(Message.session_id == session_id)
                    .order_by(Message.created_at.asc())
                )
                result = await db.execute(query)
                message_dicts = [
                    {
                        "role": m.role,
                        "content": _format_message_for_model(
                            m.role,
                            m.content,
                            _decode_message_context(getattr(m, "message_context", None)),
                        ),
                    }
                    for m in result.scalars().all()
                ]

        if not summary_provider or len(message_dicts) <= 15:
            return message_dicts

        try:
            from backend.modules.agent.memory import ConversationSummarizer

            summarizer = ConversationSummarizer(provider=summary_provider, char_limit=2000)
            if not summarizer.should_summarize(message_dicts):
                return message_dicts

            to_summarize, to_keep = summarizer.get_messages_to_keep(
                message_dicts,
                keep_recent=10,
            )
            summary = await summarizer.summarize_conversation(to_summarize)
            if not summary:
                return message_dicts

            return [
                {
                    "role": "system",
                    "content": f"## Previous Conversation Summary\n\n{summary}",
                }
            ] + to_keep
        except Exception as exc:
            logger.warning(f"Failed to summarize channel history for {session_id}: {exc}")
            return message_dicts

    # ------------------------------------------------------------------
    # 任务管理
    # ------------------------------------------------------------------

    async def cancel_task(self, session_id: str) -> bool:
        """取消指定会话的活跃任务。"""
        if session_id in self._active_tasks:
            self._active_tasks[session_id].cancel()
            logger.info(f"Cancelled task for session {session_id}")
            return True
        return False

    def get_active_tasks(self) -> List[str]:
        """获取所有活跃任务的会话 ID。"""
        return list(self._active_tasks.keys())

    async def get_queue_stats(self) -> dict:
        """获取队列统计信息。"""
        return {
            "inbound_size": self.bus.inbound_size,
            "outbound_size": self.bus.outbound_size,
            "active_tasks": len(self._active_tasks),
            "rate_limiter": self.rate_limiter.get_stats() if self.rate_limiter else None,
        }
