"""Cron 任务执行器"""

import json
from datetime import datetime
from typing import Any, Optional

from backend.modules.agent.loop import AgentLoop
from backend.modules.agent.prompts import CRON_TASK_EXECUTION_PROMPT
from backend.modules.messaging.enterprise_queue import EnterpriseMessageQueue
from backend.modules.session.manager import SessionManager
from backend.modules.channels.manager import ChannelManager
from backend.utils.logger import logger

# Heartbeat 特殊消息标记
HEARTBEAT_MESSAGE_MARKER = "__heartbeat__"
PRIMARY_ACCOUNT_ID = "default"
PRIMARY_GROUP_SHARED_CHANNELS = {"wecom", "feishu", "dingtalk", "qq"}



class CronExecutor:
    """定时任务执行器"""

    def __init__(
        self,
        agent: AgentLoop,
        bus: EnterpriseMessageQueue,
        session_manager: SessionManager,
        channel_manager: Optional[ChannelManager] = None,
        heartbeat_service=None,
    ):
        self.agent = agent
        self.bus = bus
        self.session_manager = session_manager
        self.channel_manager = channel_manager
        self.heartbeat_service = heartbeat_service

    async def execute(
        self,
        job_id: str,
        message: str,
        channel: Optional[str] = None,
        account_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        deliver_response: bool = False
    ) -> str:
        """执行定时任务"""
        logger.info(f"Executing job {job_id}: {message[:100]}...")

        # 识别 heartbeat 特殊任务
        if message == HEARTBEAT_MESSAGE_MARKER:
            return await self._execute_heartbeat(
                job_id,
                channel,
                account_id,
                chat_id,
                deliver_response,
            )

        try:
            # 如果有 channel 和 chat_id，查找或创建对应的会话
            if channel and chat_id:
                session_id = await self._get_or_create_session(channel, account_id, chat_id)
            else:
                session_id = f"cron:{job_id}"

            # 使用专用的 cron 任务提示词包装消息
            cron_message = CRON_TASK_EXECUTION_PROMPT.format(task_message=message)

            response = await self.agent.process_direct(
                content=cron_message,
                session_id=session_id,
                channel=channel or "cron",
                chat_id=chat_id or job_id,
                account_id=account_id,
            )

            logger.info(f"Job {job_id} completed")

            # 如果有 channel 和 chat_id，保存消息到数据库（与频道消息保持一致）
            if channel and chat_id and response:
                await self._save_messages_to_db(session_id, message, response)

            if deliver_response and response and channel and chat_id:
                await self._deliver_to_channel(
                    channel=channel,
                    account_id=account_id,
                    chat_id=chat_id,
                    message=response,
                    job_id=job_id
                )

            return response or ""

        except Exception as e:
            logger.error(f"Cron job {job_id} failed: {e}")
            raise

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
            greeting = await self.heartbeat_service.execute()
            if not greeting:
                return ""

            # 通过渠道投递问候（复用定时任务的渠道投递）
            if channel and chat_id:
                await self._deliver_to_channel(
                    channel=channel,
                    account_id=account_id,
                    chat_id=chat_id,
                    message=greeting,
                    job_id=job_id,
                )
                
                # 将问候语保存到会话历史中，以便用户回复时 AI 能看到上下文
                await self._save_greeting_to_session(
                    channel=channel,
                    account_id=account_id,
                    chat_id=chat_id,
                    greeting=greeting,
                )
            else:
                logger.warning(
                    "Heartbeat: no channel/chat_id configured on heartbeat cron job, "
                    "greeting generated but not delivered. "
                    "Please configure channel and chat_id in the cron job settings."
                )

            return greeting
        except Exception as e:
            logger.error(f"Heartbeat execution failed: {e}")
            return ""

    async def _deliver_to_channel(
        self,
        channel: str,
        account_id: Optional[str],
        chat_id: str,
        message: str,
        job_id: str
    ):
        """发送响应到渠道"""
        try:
            if not self.channel_manager:
                logger.warning(f"Channel manager unavailable")
                return

            normalized_account_id = self._normalize_account_id(account_id)
            channel_instance = self.channel_manager.get_channel(
                channel,
                account_id=normalized_account_id,
            )
            if not channel_instance:
                logger.warning(f"Channel {channel}:{normalized_account_id} not found")
                return

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

        except Exception as e:
            logger.error(f"Failed to deliver: {e}")

    async def _save_greeting_to_session(
        self,
        channel: str,
        account_id: Optional[str],
        chat_id: str,
        greeting: str,
    ):
        """将问候语保存到会话历史中"""
        try:
            from backend.database import get_db_session_factory
            from backend.models.message import Message
            
            # 获取或创建会话
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
                
        except Exception as e:
            logger.error(f"Failed to save greeting to session: {e}")

    @staticmethod
    def _normalize_account_id(account_id: Optional[str]) -> str:
        return str(account_id or PRIMARY_ACCOUNT_ID).strip() or PRIMARY_ACCOUNT_ID

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
                .where(Session.name.like(f"{prefix}%"))
                .order_by(Session.created_at.desc())
                .limit(1)
            )
            session = result.scalar_one_or_none()

            if not session and normalized_account_id == PRIMARY_ACCOUNT_ID:
                result = await db.execute(
                    select(Session)
                    .where(Session.name.like(f"{legacy_prefix}%"))
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

    async def _save_messages_to_db(self, session_id: str, user_message: str, ai_response: str):
        """将定时任务的消息保存到数据库（与频道消息保持一致）"""
        try:
            from backend.database import get_db_session_factory
            from backend.models.message import Message
            
            db_factory = get_db_session_factory()
            async with db_factory() as db:
                # 保存用户消息（定时任务的提示词）
                db.add(Message(
                    session_id=session_id,
                    role="user",
                    content=user_message,
                ))
                
                # 保存 AI 响应
                db.add(Message(
                    session_id=session_id,
                    role="assistant",
                    content=ai_response,
                ))
                
                await db.commit()
                logger.debug(f"Saved cron messages to session {session_id}")
                
        except Exception as e:
            logger.error(f"Failed to save cron messages to DB: {e}")


