"""频道消息处理器模块

处理来自所有频道的入站消息，集成 Agent 循环进行回复。
与 WebSocket 端共享 context_builder / subagent_manager / tool_params，
确保频道和网页 UI 使用完全一致的提示词、技能、工具。
"""

import asyncio
import time
from pathlib import Path
from typing import Dict, List, Optional

from loguru import logger

from backend.database import get_db_session_factory
from backend.models.message import Message
from backend.models.session import Session
from backend.modules.agent.context import ContextBuilder
from backend.modules.agent.loop import AgentLoop
from backend.modules.agent.session_gate import get_session_gate
from backend.modules.agent.task_manager import CancellationToken
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
from backend.modules.session import (
    build_session_model_override,
    resolve_session_runtime_config,
)
from backend.modules.tools.setup import register_all_tools
from backend.modules.channels.inbound_utils import (
    _PRIMARY_ACCOUNT_ID,
    _WORKFLOW_META_RE,
    _build_history_message,
    _decode_message_context,
    _encode_message_context,
    _format_bot_label,
    _format_message_for_model,
    _friendly_channel_error,
    _is_group_message,
    _normalize_assistant_output,
    _normalize_channel_inbound_content,
    _resolve_session_route,
    _validate_runtime_provider,
)
from backend.modules.channels.commands import ChannelCommandMixin
from backend.modules.channels.sessions import ChannelSessionMixin
from backend.modules.channels.persistence import ChannelPersistenceMixin



def _log_handle_task_exception(task: "asyncio.Task") -> None:
    """收集 handle_message 后台任务的未处理异常，避免被静默吞掉。"""
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error(f"handle_message task failed: {exc!r}")


class ChannelMessageHandler(
    ChannelCommandMixin,
    ChannelSessionMixin,
    ChannelPersistenceMixin,
):
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

    def _reconcile_mcp_tools(self) -> None:
        """每轮消息前，把本 handler 的注册表与当前全局 MCP 工具集对齐。

        与 WS 对话同理：本注册表在整个 handler 生命周期内复用，若不重新对齐，
        中途改了 MCP 配置后老会话就加载不到最新工具。
        """
        try:
            from backend.modules.mcp.client import McpClientManager
            McpClientManager.get_instance().reconcile_registry_sync(self.tool_registry)
        except Exception as exc:
            logger.debug(f"MCP reconcile skipped: {exc}")

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
        injection_config=None,
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

        if injection_config is not None:
            # 注入开关热重载：同步 context_builder 与工具禁用列表
            self.context_builder.update_injection_config(injection_config)
            disabled_tools = list(injection_config.disabled_tools)
            if self._tool_params.get("disabled_tools") != disabled_tools:
                self._tool_params["disabled_tools"] = disabled_tools
                should_rebuild_tools = True
            logger.info(
                f"Injection config reloaded: disabled_tools={disabled_tools}, "
                f"auto_memory_summary={injection_config.auto_memory_summary}"
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
                task = asyncio.create_task(self.handle_message(msg))
                # 显式收集后台任务异常：任务内未处理异常默认只留下
                # "Task exception was never retrieved"，容易被漏看
                task.add_done_callback(_log_handle_task_exception)
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
        turn_token_acquired = False
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
            content = await self._promote_inbound_media(msg, content)
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

            # 同一会话已有处理在进行时，本条消息不并发开跑，而是登记为插话：
            # 由正在执行的那一轮在工具批次之间取走并合并进上下文，用户看到的是
            # 一次连续回复，而不是两条互相踩踏的并发回复。
            gate = get_session_gate()
            if gate.is_busy(session_id):
                # 先落库再登记：插话只会被「正在进行的那一轮」合并进上下文，
                # 若不入库，下一轮从数据库重建历史时就彻底看不到这条消息了。
                # 由排队补救流程重新投递的消息此前已落库，不能重复写入。
                if not (msg.metadata or {}).get("_persisted"):
                    await self._save_message(
                        session_id,
                        "user",
                        content,
                        message_context=user_message_context,
                    )
                entry = gate.enqueue_pending(session_id, content)
                logger.info(
                    f"[{msg.channel}] Session {session_id} busy, message queued "
                    f"for in-flight turn (pending_id={entry.id})"
                )
                await self._maybe_notify_queued(msg, session_id)
                return

            await gate.acquire(session_id)
            turn_token_acquired = True
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
            self._reconcile_mcp_tools()
            workflow_tool = self.tool_registry.get_tool("workflow_run")
            if workflow_tool and hasattr(workflow_tool, "set_event_callback"):
                workflow_tool.set_event_callback(tool_event_handler)
            # 由排队补救流程重新投递的消息此前已落库，跳过重复写入
            already_persisted = bool((msg.metadata or {}).get("_persisted"))
            if not already_persisted:
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
                    pending_message_provider=lambda: get_session_gate().take_pending(session_id),
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
            # 只清理自己登记的令牌：并发排队时后者不能误删前者的引用
            if session_id and self._active_tasks.get(session_id) is cancel_token:
                del self._active_tasks[session_id]
            if turn_token_acquired:
                # 本轮结束前若还有没被消费的插话（例如本轮被取消、异常退出，
                # 或直接走了 workflow 结果返回路径），把它重新投递回队列，
                # 让它在下一轮被正常处理，而不是烂在内存里。
                leftover = get_session_gate().drain_pending(session_id)
                if leftover and not cancel_token.is_cancelled:
                    try:
                        requeue_metadata = dict(msg.metadata or {})
                        # 这些内容在登记为插话时已经落库，重新处理时不能再写一次；
                        # 同时清掉本轮残留的流式回调，避免旧的发送句柄被复用。
                        requeue_metadata["_persisted"] = True
                        requeue_metadata.pop("_stream_handler", None)
                        requeue_metadata.pop("_stream_abort_handler", None)
                        requeue_metadata.pop("_tool_event_handler", None)
                        await self.bus.publish_inbound(
                            InboundMessage(
                                channel=msg.channel,
                                sender_id=msg.sender_id,
                                chat_id=msg.chat_id,
                                content="\n".join(leftover),
                                media=None,
                                metadata=requeue_metadata,
                            )
                        )
                        logger.info(
                            f"[{msg.channel}] Re-queued {len(leftover)} unconsumed "
                            f"message(s) for session {session_id}"
                        )
                    except Exception as exc:
                        logger.warning(
                            f"[{msg.channel}] Failed to re-queue unconsumed messages: {exc}"
                        )
                get_session_gate().release(session_id)

    async def _maybe_notify_queued(self, msg: InboundMessage, session_id: str) -> None:
        """群聊忙碌时通过渠道能力发送排队卡片（目前由飞书实现）。"""
        if self.channel_manager is None or not _is_group_message(msg):
            return

        metadata = msg.metadata or {}
        account_id = str(metadata.get("account_id") or "default").strip() or "default"
        channel = self.channel_manager.get_channel(msg.channel, account_id=account_id)
        if channel is None or not hasattr(channel, "notify_queued"):
            return

        try:
            position = get_session_gate().pending_count(session_id)
            await channel.notify_queued(msg, position=position)
        except Exception as e:
            logger.debug(f"[{msg.channel}] Failed to send queue notice: {e}")

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
                pending_message_provider=lambda: get_session_gate().take_pending(session_id),
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
    # 路由偏好与外部编码代理
    # ------------------------------------------------------------------

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
        # 外部编码代理是长任务，同样按会话串行：同一会话不允许两条指令并发下发。
        gate = get_session_gate()
        turn_acquired = False
        if gate.is_busy(session_id):
            await self._send_reply(msg, "当前会话还有任务在执行，请等它结束后再试。")
            return
        try:
            # acquire 到 release 之间的代码都在本 try 内，
            # 任何异常路径都能走到 finally 的 release。
            await gate.acquire(session_id)
            turn_acquired = True
            self._active_tasks[session_id] = cancel_token
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
            self._reconcile_mcp_tools()

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
            # 与 handle_message / _handle_team_command 的 finally 对齐：
            # 清掉本轮设置的会话上下文，避免工具注册表把 channel/session
            # 上下文残留到下一个会话的第一次工具调用。
            self.tool_registry.set_cancel_token(None)
            self.tool_registry.set_message_context(None)
            self._active_tasks.pop(session_id, None)
            if turn_acquired:
                get_session_gate().release(session_id)

    # ------------------------------------------------------------------
    # 任务管理
    # ------------------------------------------------------------------

    async def cancel_task(self, session_id: str) -> bool:
        """取消指定会话的活跃任务。"""
        # 用户要求停止时，排队等插入的消息也一并作废，避免任务刚停又被旧消息拉起
        get_session_gate().discard_pending(session_id)
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
            "session_gate": get_session_gate().stats(),
            "rate_limiter": self.rate_limiter.get_stats() if self.rate_limiter else None,
        }
