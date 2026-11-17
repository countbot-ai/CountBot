"""Cron 任务执行器"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from backend.modules.agent.loop import AgentLoop
from backend.modules.agent.prompts import CRON_TASK_EXECUTION_PROMPT, render_prompt
from backend.modules.agent.session_gate import get_session_gate
from backend.modules.cron.types import CronDeliveryError
from backend.modules.session.manager import session_name_matches
from backend.utils.logger import logger

if TYPE_CHECKING:
    from backend.modules.channels.manager import ChannelManager
    from backend.modules.messaging.enterprise_queue import EnterpriseMessageQueue

# Heartbeat 特殊消息标记
HEARTBEAT_MESSAGE_MARKER = "__heartbeat__"
PRIMARY_ACCOUNT_ID = "default"
PRIMARY_GROUP_SHARED_CHANNELS = {"wecom", "feishu", "dingtalk", "qq"}

# 渠道推送的即时重试：单次网络抖动不该直接判定任务失败
DELIVERY_MAX_ATTEMPTS = 3
DELIVERY_RETRY_DELAYS = (2, 5)

# 「关联上下文」保留的历史执行记录字符预算，超出时丢弃最旧的对话对
CONTEXT_HISTORY_MAX_CHARS = 200_000



class CronExecutor:
    """定时任务执行器"""

    def __init__(
        self,
        agent: AgentLoop,
        bus: EnterpriseMessageQueue,
        channel_manager: Optional[ChannelManager] = None,
        heartbeat_service=None,
    ):
        self.agent = agent
        self.bus = bus
        self.channel_manager = channel_manager
        self.heartbeat_service = heartbeat_service

    async def execute(
        self,
        job_id: str,
        message: str,
        channel: Optional[str] = None,
        account_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        deliver_response: bool = False,
        model_provider: Optional[str] = None,
        model_name: Optional[str] = None,
        link_context: bool = False,
    ) -> str:
        """执行定时任务"""
        # 识别 heartbeat 特殊任务
        if message == HEARTBEAT_MESSAGE_MARKER:
            return await self._execute_heartbeat(
                job_id,
                channel,
                account_id,
                chat_id,
                deliver_response,
            )

        logger.info(f"Executing job {job_id}: {message[:100]}...")

        try:
            # 定时任务始终使用独立会话，不读写渠道会话，避免把任务记录混进用户对话。
            # 开启「关联上下文」时复用任务专属会话 ID，并把历史执行记录作为上下文。
            if link_context:
                session_id = f"cron:{job_id}"
                context_messages = await self._load_context_history(job_id)
            else:
                session_id = f"cron:{job_id}:{uuid.uuid4().hex[:12]}"
                context_messages = []

            if self.agent.tools:
                self.agent.tools.set_session_id(session_id)
                self.agent.tools.set_channel(channel or "cron")

            cron_message = render_prompt(CRON_TASK_EXECUTION_PROMPT, task_message=message)
            # 关联上下文时同一任务会复用会话，仍然走会话闸门避免重试与手动触发并发写同一份记录
            gate = get_session_gate()
            await gate.acquire(session_id)
            try:
                response = await self.agent.process_direct(
                    content=cron_message,
                    session_id=session_id,
                    channel=channel or "cron",
                    chat_id=chat_id or job_id,
                    account_id=account_id,
                    context=context_messages,
                    model_override=self._build_model_override_with_level(
                        model_provider,
                        model_name,
                    ),
                )
            finally:
                gate.release(session_id)

            logger.info(f"Job {job_id} completed")

            # 关联上下文：把本轮的任务与回复追加到任务自己的记录里，供下次拼接
            if link_context and response:
                await self._append_context_history(job_id, cron_message, response)

            if deliver_response:
                await self._deliver_response_or_raise(
                    channel=channel,
                    account_id=account_id,
                    chat_id=chat_id,
                    response=response,
                    job_id=job_id,
                )

            return response or ""

        except Exception as e:
            logger.error(f"Cron job {job_id} failed: {e}")
            raise

    async def _load_context_history(self, job_id: str) -> list[dict]:
        """读取该任务之前的执行记录，作为本轮模型的上下文。"""
        from sqlalchemy import select

        from backend.database import get_db_session_factory
        from backend.models.cron_job import CronJob

        try:
            async with get_db_session_factory()() as db:
                raw = (
                    await db.execute(
                        select(CronJob.context_history).where(CronJob.id == job_id)
                    )
                ).scalar_one_or_none()
        except Exception as e:
            logger.warning(f"Failed to load context history for {job_id}: {e}")
            return []

        return self._parse_context_history(raw)

    @staticmethod
    def _parse_context_history(raw: Optional[str]) -> list[dict]:
        """解析持久化的历史执行记录，过滤掉不合法条目。"""
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except Exception:
            return []
        if not isinstance(data, list):
            return []

        messages: list[dict] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            content = item.get("content")
            if role in ("user", "assistant") and isinstance(content, str) and content.strip():
                messages.append({"role": role, "content": content})
        return messages

    async def _append_context_history(
        self,
        job_id: str,
        user_message: str,
        response: str,
    ) -> None:
        """把本轮执行记录写回任务，供下次「关联上下文」时拼接。"""
        from sqlalchemy import select

        from backend.database import get_db_session_factory
        from backend.models.cron_job import CronJob

        try:
            async with get_db_session_factory()() as db:
                job = (
                    await db.execute(select(CronJob).where(CronJob.id == job_id))
                ).scalar_one_or_none()
                if job is None:
                    return

                history = self._parse_context_history(job.context_history)
                history.append({"role": "user", "content": user_message})
                history.append({"role": "assistant", "content": response})
                job.context_history = json.dumps(
                    self._trim_context_history(history),
                    ensure_ascii=False,
                )
                await db.commit()
        except Exception as e:
            logger.warning(f"Failed to save context history for {job_id}: {e}")

    @staticmethod
    def _trim_context_history(messages: list[dict]) -> list[dict]:
        """按字符预算丢弃最旧的对话对，避免上下文无限膨胀。"""
        total = sum(len(item["content"]) for item in messages)
        while len(messages) > 2 and total > CONTEXT_HISTORY_MAX_CHARS:
            for _ in range(2):
                if len(messages) <= 2:
                    break
                total -= len(messages.pop(0)["content"])
        return messages

    async def _execute_heartbeat(
        self,
        job_id: str,
        channel: Optional[str] = None,
        account_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        deliver_response: bool = False,
    ) -> str:
        """执行 heartbeat 问候任务，复用渠道投递"""
        if not self.heartbeat_service:
            logger.warning("Heartbeat service not configured, skipping")
            return ""

        try:
            if not channel or not chat_id:
                logger.warning(
                    "主动问候已跳过：未配置推送渠道或目标 chat_id，"
                    "请在设置中补全问候助手的投递目标"
                )
                return ""

            resolved_account_id = self._resolve_channel_account_id(channel, account_id)
            session_id = await self._get_or_create_session(
                channel,
                resolved_account_id,
                chat_id,
            )
            dispatch = await self.heartbeat_service.prepare_dispatch(
                session_id=session_id,
                channel=channel,
                account_id=resolved_account_id,
                chat_id=chat_id,
            )
            if not dispatch:
                return ""

            await self._deliver_with_retry(
                channel=channel,
                account_id=resolved_account_id,
                chat_id=chat_id,
                message=dispatch.greeting,
                job_id=job_id,
            )

            # 将问候语保存到会话历史中，以便用户回复时 AI 能看到上下文
            await self._save_greeting_to_session(
                channel=channel,
                account_id=resolved_account_id,
                chat_id=chat_id,
                greeting=dispatch.greeting,
                session_id=session_id,
                strict=True,
            )

            self.heartbeat_service.commit_dispatch(dispatch)

            return dispatch.greeting
        except Exception as e:
            logger.error(f"Heartbeat execution failed: {e}")
            # 向上抛出：吞掉异常会让调度器把本次执行记为成功，
            # 投递渠道故障在面板上无法体现。
            raise

    @classmethod
    def _build_model_override_with_level(
        cls,
        model_provider: Optional[str],
        model_name: Optional[str],
    ) -> Optional[dict]:
        """在模型覆盖上补思考档位，与聊天窗口同口径：模型条目默认 > 全局设置。"""
        override = cls._build_model_override(model_provider, model_name)
        level = cls._resolve_reasoning_level(model_provider, model_name)
        if not level:
            return override
        merged = dict(override or {})
        merged["reasoning_level"] = level
        return merged

    @staticmethod
    def _resolve_reasoning_level(
        model_provider: Optional[str],
        model_name: Optional[str],
    ) -> Optional[str]:
        """取实际使用的模型条目的默认档位；未配置时回落全局设置的档位。"""
        from backend.modules.config.loader import config_loader

        config = config_loader.config
        provider_id = str(model_provider or "").strip() or config.model.provider
        model_id = str(model_name or "").strip() or config.model.model

        provider_config = config.providers.get(provider_id)
        if provider_config is not None:
            entry = provider_config.find_model(model_id)
            if entry is not None and entry.reasoning_level:
                return entry.reasoning_level
        return config.model.reasoning_level

    @staticmethod
    def _build_model_override(
        model_provider: Optional[str],
        model_name: Optional[str],
    ) -> Optional[dict]:
        """任务指定了模型时生成执行器可消费的覆盖参数。

        未指定（跟随全局默认）时返回 None；api_key / api_base 由执行器按供应商配置解析。
        """
        provider = str(model_provider or "").strip()
        model = str(model_name or "").strip()
        if not provider or not model:
            return None
        return {"provider": provider, "model": model}

    async def _deliver_response_or_raise(
        self,
        channel: Optional[str],
        account_id: Optional[str],
        chat_id: Optional[str],
        response: Optional[str],
        job_id: str,
    ) -> None:
        """把 AI 响应推送到渠道；任何一步失败都抛出 CronDeliveryError。

        开启「推送响应到渠道」后，推送就是任务的一部分：静默失败会让用户
        以为任务成功，所以这里必须显式失败并保留原因。
        """
        if not channel or not chat_id:
            raise CronDeliveryError("推送失败：任务未配置推送渠道或聊天 ID")
        if not response:
            raise CronDeliveryError("推送失败：AI 返回内容为空，没有可推送的内容")

        await self._deliver_with_retry(
            channel=channel,
            account_id=account_id,
            chat_id=chat_id,
            message=response,
            job_id=job_id,
        )

    async def _deliver_with_retry(
        self,
        channel: str,
        account_id: Optional[str],
        chat_id: str,
        message: str,
        job_id: str,
    ) -> None:
        """带重试的渠道推送；全部尝试失败后抛出 CronDeliveryError。"""
        last_error: Optional[Exception] = None

        for attempt in range(DELIVERY_MAX_ATTEMPTS):
            try:
                await self._deliver_to_channel(
                    channel=channel,
                    account_id=account_id,
                    chat_id=chat_id,
                    message=message,
                    job_id=job_id,
                    strict=True,
                )
                return
            except Exception as e:
                last_error = e
                if attempt < DELIVERY_MAX_ATTEMPTS - 1:
                    delay = DELIVERY_RETRY_DELAYS[attempt]
                    logger.warning(
                        f"Job {job_id} push failed "
                        f"({attempt + 1}/{DELIVERY_MAX_ATTEMPTS}), retry in {delay}s: {e}"
                    )
                    await asyncio.sleep(delay)

        logger.error(f"Job {job_id} push failed after {DELIVERY_MAX_ATTEMPTS} attempts: {last_error}")
        raise CronDeliveryError(
            f"推送失败（已重试 {DELIVERY_MAX_ATTEMPTS} 次）：{last_error}"
        ) from last_error

    async def _deliver_to_channel(
        self,
        channel: str,
        account_id: Optional[str],
        chat_id: str,
        message: str,
        job_id: str,
        *,
        strict: bool = False,
    ) -> bool:
        """发送响应到渠道"""
        try:
            if not self.channel_manager:
                error = "Channel manager unavailable"
                if strict:
                    raise RuntimeError(error)
                logger.warning(error)
                return False

            normalized_account_id = self._resolve_channel_account_id(channel, account_id)
            channel_instance = self.channel_manager.get_channel(
                channel,
                account_id=normalized_account_id,
            )
            if not channel_instance:
                error = f"Channel {channel}:{normalized_account_id} not found"
                if strict:
                    raise RuntimeError(error)
                logger.warning(error)
                return False

            logger.info(f"Delivering to {channel}:{normalized_account_id}:{chat_id}")

            from backend.modules.channels.base import OutboundMessage
            await channel_instance.send(
                OutboundMessage(
                    channel=channel,
                    chat_id=chat_id,
                    content=message,
                    metadata={"account_id": normalized_account_id},
                )
            )

            logger.info(f"Delivered to {channel}:{normalized_account_id}:{chat_id}")
            return True

        except Exception as e:
            if strict:
                raise
            logger.error(f"Failed to deliver: {e}")
            return False

    async def _save_greeting_to_session(
        self,
        channel: str,
        account_id: Optional[str],
        chat_id: str,
        greeting: str,
        *,
        session_id: Optional[str] = None,
        strict: bool = False,
    ) -> bool:
        """将问候语保存到会话历史中"""
        try:
            from backend.database import get_db_session_factory
            from backend.models.message import Message
            
            # 获取或创建会话
            if not session_id:
                session_id = await self._get_or_create_session(channel, account_id, chat_id)
            
            # 保存 AI 的问候消息到数据库
            db_factory = get_db_session_factory()
            async with db_factory() as db:
                # 保存问候消息
                message = Message(
                    session_id=session_id,
                    role="assistant",
                    content=greeting,
                )
                db.add(message)
                await db.commit()
                
                logger.info(f"Greeting saved to session {session_id}")
                return True
                
        except Exception as e:
            if strict:
                raise
            logger.error(f"Failed to save greeting to session: {e}")
            return False

    @staticmethod
    def _normalize_account_id(account_id: Optional[str]) -> str:
        return str(account_id or PRIMARY_ACCOUNT_ID).strip() or PRIMARY_ACCOUNT_ID

    def _resolve_channel_account_id(self, channel: str, account_id: Optional[str]) -> str:
        """将默认账号解析为当前渠道真实可用实例，避免单机器人隐藏账号后路由失真。"""
        normalized_account_id = self._normalize_account_id(account_id)
        if not self.channel_manager:
            return normalized_account_id

        exact_channel = self.channel_manager.get_channel(channel, account_id=normalized_account_id)
        if exact_channel:
            return str(getattr(exact_channel, "account_id", normalized_account_id) or normalized_account_id)

        if normalized_account_id == PRIMARY_ACCOUNT_ID:
            fallback_channel = self.channel_manager.get_channel(channel)
            if fallback_channel:
                resolved_account_id = str(
                    getattr(fallback_channel, "account_id", normalized_account_id) or normalized_account_id
                )
                if resolved_account_id != normalized_account_id:
                    logger.info(
                        f"Auto-resolved channel account for {channel}: "
                        f"{normalized_account_id} -> {resolved_account_id}"
                    )
                return resolved_account_id

        return normalized_account_id

    @staticmethod
    def _is_group_chat(channel: str, chat_id: str) -> bool:
        if channel == "feishu":
            return str(chat_id).startswith("oc_")
        return False

    def _build_channel_context(
        self,
        channel: str,
        account_id: Optional[str],
        chat_id: str,
    ) -> dict[str, Any]:
        normalized_account_id = self._normalize_account_id(account_id)
        is_group = self._is_group_chat(channel, chat_id)
        supports_primary_group_shared = channel in PRIMARY_GROUP_SHARED_CHANNELS
        session_scope = (
            "group_shared_primary"
            if is_group and supports_primary_group_shared and normalized_account_id == PRIMARY_ACCOUNT_ID
            else ("group_independent" if is_group else "private_independent")
        )

        return {
            "channel": channel,
            "account_id": normalized_account_id,
            "sender_id": "",
            "chat_id": str(chat_id),
            "source_account_id": normalized_account_id,
            "reply_account_id": normalized_account_id,
            "context_owner_account_id": normalized_account_id,
            "primary_account_id": PRIMARY_ACCOUNT_ID,
            "session_scope": session_scope,
            "supports_primary_group_shared": supports_primary_group_shared,
            "is_group": is_group,
            "delivery_mode": "chat" if is_group else "user",
            "to_user": None if is_group else str(chat_id),
            "group_chat_id": str(chat_id) if is_group else None,
        }

    async def _get_or_create_session(
        self,
        channel: str,
        account_id: Optional[str],
        chat_id: str,
    ) -> str:
        """获取或创建频道会话（与 handler 逻辑一致）"""
        from backend.database import get_db_session_factory
        from backend.models.session import Session
        from sqlalchemy import select
        import uuid

        normalized_account_id = self._normalize_account_id(account_id)
        prefix = f"{channel}:{normalized_account_id}:{chat_id}"
        legacy_prefix = f"{channel}:{chat_id}"
        channel_context = self._build_channel_context(channel, normalized_account_id, chat_id)
        db_factory = get_db_session_factory()
        
        async with db_factory() as db:
            # 查找已有会话
            result = await db.execute(
                select(Session)
                .where(session_name_matches(prefix))
                .order_by(Session.created_at.desc())
                .limit(1)
            )
            session = result.scalar_one_or_none()

            if not session and normalized_account_id == PRIMARY_ACCOUNT_ID:
                result = await db.execute(
                    select(Session)
                    .where(session_name_matches(legacy_prefix))
                    .order_by(Session.created_at.desc())
                    .limit(1)
                )
                session = result.scalar_one_or_none()

            if session:
                existing_context = {}
                try:
                    raw_context = getattr(session, "channel_context", None)
                    if raw_context:
                        existing_context = json.loads(raw_context)
                except Exception:
                    existing_context = {}
                if channel_context != existing_context:
                    session.channel_context = json.dumps(channel_context, ensure_ascii=False)
                    await db.commit()
                return session.id
            
            # 创建新会话
            session_name = (
                f"{channel}:{normalized_account_id}:{chat_id}:"
                f"{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            )
            session = Session(
                id=str(uuid.uuid4()),
                name=session_name,
                channel_context=json.dumps(channel_context, ensure_ascii=False),
            )
            db.add(session)
            await db.commit()
            await db.refresh(session)
            logger.info(f"Created session {session.id} for {session_name}")
            return session.id


