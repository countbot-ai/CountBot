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
from backend.modules.agent.context import ContextBuilder
from backend.modules.agent.loop import AgentLoop
from backend.modules.agent.session_gate import get_session_gate
from backend.modules.agent.task_manager import CancellationToken
from backend.modules.channels.base import InboundMessage, OutboundMessage
from backend.modules.messaging.enterprise_queue import EnterpriseMessageQueue
from backend.modules.messaging.rate_limiter import RateLimiter
from backend.modules.session import build_session_model_override
from backend.modules.tools.setup import register_all_tools
from backend.modules.channels.inbound_utils import (
    _format_message_for_model,
    _friendly_channel_error,
    _is_group_message,
    _normalize_channel_inbound_content,
    _resolve_session_route,
    _validate_runtime_provider,
)
from backend.modules.channels.commands import ChannelCommandMixin
from backend.modules.channels.sessions import ChannelSessionMixin
from backend.modules.channels.persistence import ChannelPersistenceMixin
from backend.modules.channels.turn import ChannelAgentTurnMixin
from backend.modules.channels.direct_route import ChannelDirectRouteMixin



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
    ChannelAgentTurnMixin,
    ChannelDirectRouteMixin,
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
        max_iterations: int = 0,
        rate_limiter: Optional[RateLimiter] = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        thinking_enabled: bool = True,
        stream_enabled: bool = True,
        reasoning_level: Optional[str] = None,
        max_history_messages: int = 50,
        memory_store=None,
    ):
        self.bus = bus
        self.rate_limiter = rate_limiter
        # 渠道会话归属：普通用户机器人写入自己的 owner_id，管理员为空
        self._owner_id: Optional[str] = None
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
            stream_enabled=stream_enabled,
            reasoning_level=reasoning_level,
        )

    @classmethod
    def for_runtime(
        cls,
        runtime,
        *,
        bus,
        rate_limiter=None,
        max_history_messages: int = 50,
    ) -> "ChannelMessageHandler":
        """用用户运行时直接构造处理器，复用其 AgentLoop 与工具。"""
        handler = cls.__new__(cls)
        handler.bus = bus
        handler.rate_limiter = rate_limiter
        handler._owner_id = runtime.user_id
        handler._active_tasks = {}
        handler._last_session_list_scope = {}
        handler._route_mode_overrides = {}
        handler._coder_profile_overrides = {}
        handler.db_session_factory = get_db_session_factory()
        handler.channel_manager = None
        handler.max_history_messages = max_history_messages
        handler.context_builder = runtime.context_builder
        handler._tool_params = {}
        handler._subagent_manager = runtime.subagent_manager
        handler._memory_store = runtime.memory
        handler.tool_registry = runtime.tools
        handler.agent_loop = runtime.agent_loop
        return handler

    def _rebuild_tool_registry(self) -> None:
        """按最新参数重建工具注册表；用户运行时自带工具时跳过。"""
        if not self._tool_params:
            return
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
        stream_enabled: Optional[bool] = None,
        reasoning_level: Optional[str] = None,
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
        if stream_enabled is not None:
            self.agent_loop.stream_enabled = stream_enabled
        if reasoning_level is not None:
            self.agent_loop.reasoning_level = reasoning_level
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
            if await self._dispatch_command(
                msg,
                content,
                session_route=session_route,
                user_message_context=user_message_context,
                cancel_token=cancel_token,
                tool_event_handler=tool_event_handler,
                start_time=start_time,
            ):
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
                # 先落库再登记：插话由正在执行的那一轮合并进上下文，
                # 未入库的消息在下一轮从数据库重建历史时不可见。
                # 排队补救流程重新投递的消息此前已完成入库，不重复写入。
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
            active_provider, _, _, _, _, _, _, _ = self.agent_loop._resolve_execution_runtime(
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

            if stream_handler:
                response, response_reasoning = await self._run_streaming_turn(
                    msg=msg,
                    session_id=session_id,
                    model_input=model_input,
                    history=history,
                    cancel_token=cancel_token,
                    stream_handler=stream_handler,
                    tool_event_handler=tool_event_handler,
                    model_override=model_override,
                    persona_override=persona_override,
                    prefer_direct_workflow_result=prefer_direct_workflow_result,
                )
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
                await self._persist_and_send_response(
                    msg=msg,
                    session_id=session_id,
                    content=content,
                    response=response,
                    response_reasoning=response_reasoning,
                    session_route=session_route,
                    stream_handler=stream_handler,
                    start_time=start_time,
                )
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
            await self._cleanup_turn(
                msg=msg,
                session_id=session_id,
                cancel_token=cancel_token,
                turn_token_acquired=turn_token_acquired,
                typing_session_key=typing_session_key,
            )

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
