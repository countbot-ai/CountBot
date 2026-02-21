"""Cron 任务执行器"""

from typing import Optional

from backend.modules.agent.loop import AgentLoop
from backend.modules.messaging.enterprise_queue import EnterpriseMessageQueue
from backend.modules.session.manager import SessionManager
from backend.modules.channels.manager import ChannelManager
from backend.utils.logger import logger

# Heartbeat 特殊消息标记
HEARTBEAT_MESSAGE_MARKER = "__heartbeat__"



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
        chat_id: Optional[str] = None,
        deliver_response: bool = False
    ) -> str:
        """执行定时任务"""
        logger.info(f"Executing job {job_id}: {message[:100]}...")

        # 识别 heartbeat 特殊任务
        if message == HEARTBEAT_MESSAGE_MARKER:
            return await self._execute_heartbeat(job_id, channel, chat_id, deliver_response)

        try:
            # 如果有 channel 和 chat_id，查找或创建对应的会话
            if channel and chat_id:
                session_id = await self._get_or_create_session(channel, chat_id)
            else:
                session_id = f"cron:{job_id}"
            
            response = await self.agent.process_direct(
                content=message,
                session_id=session_id,
                channel=channel or "cron",
                chat_id=chat_id or job_id
            )

            logger.info(f"Job {job_id} completed")

            # 如果有 channel 和 chat_id，保存消息到数据库（与频道消息保持一致）
            if channel and chat_id and response:
                await self._save_messages_to_db(session_id, message, response)

            if deliver_response and response and channel and chat_id:
                await self._deliver_to_channel(
                    channel=channel,
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
                    chat_id=chat_id,
                    message=greeting,
                    job_id=job_id,
                )
                
                # 将问候语保存到会话历史中，以便用户回复时 AI 能看到上下文
                await self._save_greeting_to_session(
                    channel=channel,
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
        chat_id: str,
        message: str,
        job_id: str
    ):
        """发送响应到渠道"""
        try:
            if not self.channel_manager:
                logger.warning(f"Channel manager unavailable")
                return

            channel_instance = self.channel_manager.get_channel(channel)
            if not channel_instance:
                logger.warning(f"Channel {channel} not found")
                return

            logger.info(f"Delivering to {channel}:{chat_id}")

            from backend.modules.channels.base import OutboundMessage
            await channel_instance.send(
                OutboundMessage(
                    channel=channel,
                    chat_id=chat_id,
                    content=message
                )
            )

            logger.info(f"Delivered to {channel}:{chat_id}")

        except Exception as e:
            logger.error(f"Failed to deliver: {e}")

    async def _save_greeting_to_session(
        self,
        channel: str,
        chat_id: str,
        greeting: str,
    ):
        """将问候语保存到会话历史中"""
        try:
            from backend.database import get_db_session_factory
            from backend.models.message import Message
            
            # 获取或创建会话
            session_id = await self._get_or_create_session(channel, chat_id)
            
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

    async def _get_or_create_session(self, channel: str, chat_id: str) -> str:
        """获取或创建频道会话（与 handler 逻辑一致）"""
        from backend.database import get_db_session_factory
        from backend.models.session import Session
        from sqlalchemy import select
        import uuid
        
        session_name = f"{channel}:{chat_id}"
        db_factory = get_db_session_factory()
        
        async with db_factory() as db:
            # 查找已有会话
            result = await db.execute(
                select(Session)
                .where(Session.name == session_name)
                .order_by(Session.created_at.desc())
                .limit(1)
            )
            session = result.scalar_one_or_none()
            
            if session:
                return session.id
            
            # 创建新会话
            session = Session(id=str(uuid.uuid4()), name=session_name)
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


