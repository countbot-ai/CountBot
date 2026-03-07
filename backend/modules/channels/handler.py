"""频道消息处理器模块

处理来自所有频道的入站消息，集成 Agent 循环进行回复。
与 WebSocket 端共享 context_builder / subagent_manager / tool_params，
确保频道和网页 UI 使用完全一致的提示词、技能、工具。
"""

import asyncio
import re
import time
from pathlib import Path

from loguru import logger

from backend.database import get_db_session_factory
from backend.models.message import Message
from backend.models.session import Session
from backend.modules.agent.context import ContextBuilder
from backend.modules.agent.loop import AgentLoop
from backend.modules.agent.task_manager import CancellationToken
from backend.modules.channels.base import InboundMessage, OutboundMessage
from backend.modules.messaging.enterprise_queue import EnterpriseMessageQueue
from backend.modules.messaging.rate_limiter import RateLimiter
from backend.modules.providers.litellm_provider import LiteLLMProvider
from backend.modules.tools.setup import register_all_tools

# 预编译 @mention 清理正则
# 飞书格式: @_user_数字 (如 @_user_1)
# 企业微信/钉钉格式: <at user_id="xxx">@用户名</at>
_AT_MENTION_RE = re.compile(r"@_user_\d+\s*|<at[^>]*>.*?</at>\s*", re.IGNORECASE)
# 工作流执行元数据注释（用于前端面板持久化，频道输出时需剥离）
_WORKFLOW_META_RE = re.compile(r"<!--WORKFLOW_EXEC:.*?:WORKFLOW_EXEC-->", re.DOTALL)


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
        provider: LiteLLMProvider,
        workspace: Path,
        model: str,
        bus: EnterpriseMessageQueue,
        context_builder: ContextBuilder,
        tool_params: dict,
        subagent_manager=None,
        max_iterations: int = 10,
        rate_limiter: RateLimiter | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        max_history_messages: int = 50,
        memory_store=None,
    ):
        self.bus = bus
        self.rate_limiter = rate_limiter
        self._active_tasks: dict[str, CancellationToken] = {}
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
        )

        logger.debug("ChannelMessageHandler initialized")

    # ------------------------------------------------------------------
    # 配置热重载
    # ------------------------------------------------------------------

    def reload_config(
        self,
        provider=None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        max_iterations: int | None = None,
        max_history_messages: int | None = None,
        persona_config=None,
        workspace=None,
    ) -> None:
        """热重载 AI 配置（前端修改设置后调用）。"""
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
        if max_history_messages is not None:
            self.max_history_messages = max_history_messages

        if persona_config is not None:
            self.context_builder.persona_config = persona_config
            logger.info(
                f"Persona reloaded: ai_name={persona_config.ai_name}, "
                f"user_name={persona_config.user_name}, "
                f"user_address={getattr(persona_config, 'user_address', '')}"
            )

        if workspace is not None:
            self.agent_loop.workspace = workspace
            self.context_builder.workspace = workspace
            if self.agent_loop.subagent_manager:
                self.agent_loop.subagent_manager.workspace = workspace
            logger.info(f"Workspace path reloaded: {workspace}")

        logger.info(
            f"Handler config reloaded: model={model}, temp={temperature}, "
            f"max_tokens={max_tokens}"
        )

    def set_channel_manager(self, channel_manager) -> None:
        """设置频道管理器，重新注册工具以支持 send_media。"""
        self.channel_manager = channel_manager
        self.tool_registry = register_all_tools(
            **self._tool_params,
            channel_manager=channel_manager,
            memory_store=self._memory_store,
        )
        self.agent_loop.tools = self.tool_registry
        logger.debug("Tools re-registered with channel_manager")

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
                logger.debug(
                    f"Consumed inbound from {msg.channel}, queue size: {self.bus.inbound_size}"
                )
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
        """处理单条入站消息：命令识别、Agent 处理、回复。"""
        cancel_token = CancellationToken()
        session_id = None
        start_time = time.time()

        try:
            logger.info(
                f"[{msg.channel}] Handling from {msg.sender_id} "
                f"(chat={msg.chat_id}): {msg.content[:50]}..."
            )

            content = _AT_MENTION_RE.sub("", msg.content).strip()

            # 限流检查
            if self.rate_limiter:
                allowed, error_msg = await self.rate_limiter.check(msg.sender_id)
                if not allowed:
                    logger.warning(f"[{msg.channel}] Rate limit for {msg.sender_id}")
                    await self._send_reply(msg, error_msg)
                    return

            # 命令分发
            cmd = content.lower()
            if cmd in ("/new", "/newsession", "/new_session", "/n"):
                await self._handle_new_session_command(msg)
                return
            if cmd in ("/list", "/sessions", "/list_sessions", "/l", "/ls"):
                await self._handle_list_sessions_command(msg)
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
            if cmd.startswith(("/provider ", "/提供商 ", "/m ")) or cmd in ("/provider", "/提供商", "/m"):
                await self._handle_provider_command(msg, content)
                return
            if cmd.startswith(("/personality ", "/性格 ", "/p ")) or cmd in ("/personality", "/性格", "/p"):
                await self._handle_personality_command(msg, content)
                return

            # Agent 处理
            session_id = await self._get_or_create_session(msg)
            self._active_tasks[session_id] = cancel_token
            logger.debug(f"[{msg.channel}] Using session {session_id}")

            if cancel_token.is_cancelled:
                return

            self.tool_registry.set_session_id(session_id)
            await self._save_message(session_id, "user", msg.content)

            history = await self._get_session_history(session_id)
            if history:
                history = history[:-1]

            logger.debug(
                f"[{msg.channel}] Agent processing with {len(history)} history messages"
            )

            response = await self._process_with_agent(
                session_id, msg.content, history, cancel_token,
                channel=msg.channel, chat_id=msg.chat_id,
            )

            if cancel_token.is_cancelled:
                logger.info(f"[{msg.channel}] Task cancelled for session {session_id}")
                await self._send_reply(msg, "Task cancelled")
                return

            if response:
                await self._save_message(session_id, "assistant", response)
                # 剥离工作流元数据注释（仅用于 Web UI 恢复面板，频道无需此内容）
                channel_response = _WORKFLOW_META_RE.sub("", response).strip()
                await self._send_reply(msg, channel_response or response)
                duration = time.time() - start_time
                logger.info(
                    f"[{msg.channel}] Handled session {session_id} in {duration:.2f}s"
                )
            else:
                logger.warning(f"[{msg.channel}] No response for session {session_id}")

        except Exception as e:
            duration = time.time() - start_time
            logger.exception(
                f"[{msg.channel}] Error after {duration:.2f}s: {e}"
            )
            await self._send_reply(msg, _friendly_channel_error(str(e)))

        finally:
            if session_id and session_id in self._active_tasks:
                del self._active_tasks[session_id]

    # ------------------------------------------------------------------
    # Agent 处理
    # ------------------------------------------------------------------

    async def _process_with_agent(
        self,
        session_id: str,
        user_message: str,
        history: list[dict],
        cancel_token: CancellationToken,
        channel: str | None = None,
        chat_id: str | None = None,
    ) -> str:
        """运行 Agent 循环并收集响应。"""
        try:
            parts = []
            async for chunk in self.agent_loop.process_message(
                message=user_message,
                session_id=session_id,
                context=history,
                channel=channel,
                chat_id=chat_id,
                cancel_token=cancel_token,  # 确保取消令牌传入 Agent 循环
                yield_intermediate=False,   # 频道模式：只取最终回复，丢弃中间迭代文本
            ):
                if cancel_token.is_cancelled:
                    break
                parts.append(chunk)
            result = "".join(parts)
            return result or "抱歉，未能生成回复，请稍后重试。"
        except Exception as e:
            logger.error(f"Agent processing error: {e}")
            return _friendly_channel_error(str(e))

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
            )
            await self.bus.publish_outbound(reply)
            logger.debug(
                f"[{original_msg.channel}] Reply queued for {original_msg.chat_id}: "
                f"{content[:50]}..."
            )
        except Exception as e:
            logger.error(f"[{original_msg.channel}] Failed to queue reply: {e}")

    # ------------------------------------------------------------------
    # 会话管理命令
    # ------------------------------------------------------------------

    async def _get_or_create_session(self, msg: InboundMessage) -> str:
        """获取已有会话或创建新会话。"""
        from sqlalchemy import select
        from datetime import datetime

        if msg.metadata and "session_id" in msg.metadata:
            return msg.metadata["session_id"]

        if hasattr(self, "_active_sessions"):
            chat_key = f"{msg.channel}:{msg.chat_id}"
            if chat_key in self._active_sessions:
                return self._active_sessions[chat_key]

        # 查找该频道和聊天的所有会话（按创建时间倒序）
        prefix = f"{msg.channel}:{msg.chat_id}"
        async with self.db_session_factory() as db:
            result = await db.execute(
                select(Session)
                .where(Session.name.like(f"{prefix}%"))
                .order_by(Session.created_at.desc())
                .limit(1)
            )
            session = result.scalar_one_or_none()
            if session:
                return session.id

            # 创建新会话，使用带时间戳的名称
            import uuid
            session_name = f"{msg.channel}:{msg.chat_id}:{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            session = Session(id=str(uuid.uuid4()), name=session_name)
            db.add(session)
            await db.commit()
            await db.refresh(session)
            logger.info(f"Created session {session.id} for {session_name}")
            return session.id

    async def _handle_new_session_command(self, msg: InboundMessage) -> None:
        """处理 /new 命令。"""
        import uuid
        from datetime import datetime

        session_name = (
            f"{msg.channel}:{msg.chat_id}:{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        session_id = str(uuid.uuid4())

        async with self.db_session_factory() as db:
            db.add(Session(id=session_id, name=session_name))
            await db.commit()

        if not hasattr(self, "_active_sessions"):
            self._active_sessions = {}
        self._active_sessions[f"{msg.channel}:{msg.chat_id}"] = session_id

        await self._send_reply(
            msg, 
            f"新会话已创建\n\n"
            f"名称: {session_name}\n"
            f"ID: {session_id}\n\n"
            f"现在可以开始新对话了"
        )

    async def _handle_list_sessions_command(self, msg: InboundMessage) -> None:
        """处理 /list 命令。"""
        from sqlalchemy import select, func

        prefix = f"{msg.channel}:{msg.chat_id}"
        async with self.db_session_factory() as db:
            result = await db.execute(
                select(Session)
                .where(Session.name.like(f"{prefix}%"))
                .order_by(Session.created_at.desc())
                .limit(10)
            )
            sessions = result.scalars().all()

        if not sessions:
            await self._send_reply(msg, "暂无会话记录\n\n使用 /n 创建第一个会话")
            return

        lines = ["会话列表 (最近10个)\n━━━━━━━━━━━━━━━━━━━━━━\n"]
        for i, s in enumerate(sessions, 1):
            async with self.db_session_factory() as db:
                count = (
                    await db.execute(
                        select(func.count(Message.id)).where(Message.session_id == s.id)
                    )
                ).scalar()
            created = s.created_at.strftime("%Y-%m-%d %H:%M")
            lines.append(
                f"[{i}] {s.name}\n"
                f"    ID: {s.id}\n"
                f"    创建: {created} | 消息: {count}\n"
            )
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("使用 /s <编号> 快速切换，如: /s 1")
        await self._send_reply(msg, "\n".join(lines))

    async def _handle_switch_session_command(
        self, msg: InboundMessage, content: str
    ) -> None:
        """处理 /switch 命令，支持数字编号或完整ID。"""
        from sqlalchemy import select

        parts = content.split(maxsplit=1)
        if len(parts) < 2:
            await self._send_reply(
                msg, 
                "参数错误\n\n"
                "用法: /s <编号|ID>\n\n"
                "使用 /l 查看会话列表"
            )
            return

        identifier = parts[1].strip()
        
        # 获取当前频道的会话列表
        prefix = f"{msg.channel}:{msg.chat_id}"
        async with self.db_session_factory() as db:
            result = await db.execute(
                select(Session)
                .where(Session.name.like(f"{prefix}%"))
                .order_by(Session.created_at.desc())
                .limit(10)
            )
            sessions = result.scalars().all()
        
        if not sessions:
            await self._send_reply(msg, "暂无会话记录")
            return
        
        # 尝试作为数字编号解析
        session = None
        if identifier.isdigit():
            index = int(identifier) - 1
            if 0 <= index < len(sessions):
                session = sessions[index]
            else:
                await self._send_reply(
                    msg,
                    f"编号 {identifier} 不存在\n\n"
                    f"当前有 {len(sessions)} 个会话\n"
                    f"使用 /l 查看列表"
                )
                return
        else:
            # 作为完整ID查找
            async with self.db_session_factory() as db:
                result = await db.execute(
                    select(Session).where(Session.id == identifier)
                )
                session = result.scalar_one_or_none()
        
        if not session:
            await self._send_reply(
                msg, 
                f"会话不存在: {identifier}\n\n"
                f"使用 /l 查看可用会话"
            )
            return

        if not hasattr(self, "_active_sessions"):
            self._active_sessions = {}
        self._active_sessions[f"{msg.channel}:{msg.chat_id}"] = session.id
        await self._send_reply(
            msg, 
            f"已切换会话\n\n"
            f"{session.name}\n"
            f"ID: {session.id}"
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
        """处理 /personality 或 /p 命令。"""
        from backend.modules.agent.personalities import PERSONALITY_PRESETS
        from backend.modules.config.loader import config_loader
        
        parts = content.split(maxsplit=1)
        
        # 如果没有参数，显示可用性格列表
        if len(parts) < 2:
            lines = ["可用性格列表\n━━━━━━━━━━━━━━━━━━━━━━\n"]
            current = config_loader.config.persona.personality
            for pid, preset in PERSONALITY_PRESETS.items():
                marker = "[当前]" if pid == current else ""
                lines.append(f"{pid} - {preset['name']} {marker}")
            lines.append("\n━━━━━━━━━━━━━━━━━━━━━━")
            lines.append(f"当前性格: {current}")
            lines.append("\n使用 /p <性格ID> 切换")
            await self._send_reply(msg, "\n".join(lines))
            return
        
        # 切换性格
        personality_id = parts[1].strip().lower()
        
        if personality_id not in PERSONALITY_PRESETS:
            await self._send_reply(
                msg,
                f"性格 '{personality_id}' 不存在\n\n"
                f"使用 /p 查看可用性格"
            )
            return
        
        config_loader.config.persona.personality = personality_id
        await config_loader.save_config(config_loader.config)
        await config_loader.load()
        
        self.reload_config(persona_config=config_loader.config.persona)
        
        preset = PERSONALITY_PRESETS[personality_id]
        await self._send_reply(
            msg,
            f"性格已切换为: {preset['name']}\n\n"
            f"{preset['description']}"
        )

    async def _handle_provider_command(self, msg: InboundMessage, content: str) -> None:
        """处理 /provider 或 /m 命令 - 切换模型提供商。"""
        from backend.modules.providers.registry import get_provider_metadata
        from backend.modules.providers.litellm_provider import LiteLLMProvider
        from backend.modules.config.loader import config_loader
        
        parts = content.split(maxsplit=1)
        
        # 如果没有参数，显示已配置的提供商列表
        if len(parts) < 2:
            lines = ["已配置的模型提供商\n━━━━━━━━━━━━━━━━━━━━━━\n"]
            current_provider = config_loader.config.model.provider
            
            available_providers = []
            for provider_id, provider_config in config_loader.config.providers.items():
                if provider_config.enabled and provider_config.api_key:
                    metadata = get_provider_metadata(provider_id)
                    if metadata:
                        available_providers.append((provider_id, metadata, provider_config))
            
            if not available_providers:
                await self._send_reply(
                    msg,
                    "暂无已配置的提供商\n\n"
                    "请在 Web 界面配置 API Key"
                )
                return
            
            for i, (provider_id, metadata, provider_config) in enumerate(available_providers, 1):
                marker = " [当前]" if provider_id == current_provider else ""
                lines.append(f"[{i}] {provider_id} - {metadata.name}{marker}")
                
                actual_model = provider_config.model or metadata.default_model
                if actual_model:
                    lines.append(f"    模型: {actual_model}")
            
            lines.append("\n━━━━━━━━━━━━━━━━━━━━━━")
            lines.append(f"当前提供商: {current_provider}")
            lines.append(f"当前模型: {config_loader.config.model.model}")
            lines.append("\n使用 /m <编号|提供商ID> 切换")
            lines.append("如: /m 1 或 /m openai")
            await self._send_reply(msg, "\n".join(lines))
            return
        
        # 切换提供商
        identifier = parts[1].strip().lower()
        
        # 获取可用提供商列表
        available_providers = []
        for provider_id, provider_config in config_loader.config.providers.items():
            if provider_config.enabled and provider_config.api_key:
                metadata = get_provider_metadata(provider_id)
                if metadata:
                    available_providers.append((provider_id, metadata, provider_config))
        
        # 尝试作为数字编号解析
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
            # 作为提供商ID查找
            metadata = get_provider_metadata(identifier)
            if metadata:
                provider_config = config_loader.config.providers.get(identifier)
                if provider_config and provider_config.enabled and provider_config.api_key:
                    provider_id = identifier
        
        if not provider_id or not metadata or not provider_config:
            await self._send_reply(
                msg,
                f"提供商 '{identifier}' 不存在或未配置\n\n"
                f"使用 /m 查看可用提供商"
            )
            return
        
        # 更新配置
        old_provider = config_loader.config.model.provider
        old_model = config_loader.config.model.model
        
        if old_provider in config_loader.config.providers:
            old_provider_config = config_loader.config.providers[old_provider]
            if old_provider_config.model != old_model:
                old_provider_config.model = old_model
        
        config_loader.config.model.provider = provider_id
        
        new_model = provider_config.model
        if not new_model:
            new_model = metadata.default_model
            if new_model and not provider_config.model:
                provider_config.model = new_model
        
        if new_model:
            config_loader.config.model.model = new_model
        
        await config_loader.save_config(config_loader.config)
        await config_loader.load()
        
        api_key = provider_config.api_key
        api_base = provider_config.api_base or metadata.default_api_base
        
        new_provider = LiteLLMProvider(
            api_key=api_key,
            api_base=api_base,
            default_model=config_loader.config.model.model,
            timeout=120.0,
            max_retries=3,
            provider_id=provider_id,
        )
        
        self.reload_config(
            provider=new_provider,
            model=config_loader.config.model.model
        )
        
        await self._send_reply(
            msg,
            f"提供商已切换\n\n"
            f"从: {old_provider} ({old_model})\n"
            f"到: {provider_id} ({config_loader.config.model.model})\n\n"
            f"现在使用新提供商回复"
        )

    async def _handle_help_command(self, msg: InboundMessage) -> None:
        """处理 /help 命令。"""
        help_text = (
            "可用命令\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "会话管理:\n"
            "  /new (/n) - 创建新会话\n"
            "  /list (/l) - 查看最近10个会话\n"
            "  /switch (/s) <编号|ID> - 切换会话\n"
            "  /clear (/c) - 清除当前会话历史\n\n"
            "个性化设置:\n"
            "  /personality (/p) - 查看/切换性格\n"
            "  /provider (/m) - 查看/切换模型提供商\n\n"
            "控制:\n"
            "  /stop - 停止当前任务\n"
            "  /help (/h) - 显示此帮助\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "提示: 直接发消息即可对话\n"
            "括号内为命令简写，如 /p 等同于 /personality\n"
        )
        await self._send_reply(msg, help_text)

    # ------------------------------------------------------------------
    # 数据库辅助
    # ------------------------------------------------------------------

    async def _save_message(self, session_id: str, role: str, content: str) -> None:
        """保存消息到数据库。"""
        async with self.db_session_factory() as db:
            db.add(Message(session_id=session_id, role=role, content=content))
            await db.commit()

    async def _get_session_history(self, session_id: str) -> list[dict]:
        """获取会话历史消息。"""
        from sqlalchemy import select

        limit = self.max_history_messages if self.max_history_messages != -1 else None

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
                return [
                    {"role": m.role, "content": m.content} for m in reversed(messages)
                ]
            else:
                query = (
                    select(Message)
                    .where(Message.session_id == session_id)
                    .order_by(Message.created_at.asc())
                )
                result = await db.execute(query)
                return [
                    {"role": m.role, "content": m.content}
                    for m in result.scalars().all()
                ]

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

    def get_active_tasks(self) -> list[str]:
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
