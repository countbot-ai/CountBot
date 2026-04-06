"""会话管理器"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models.message import Message
from backend.models.session import Session


class SessionManager:
    """会话管理器 - 负责会话的 CRUD 操作、消息管理和会话持久化"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_session(self, name: str) -> Session:
        """创建新会话"""
        session = Session(
            id=str(uuid.uuid4()),
            name=name,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def get_session(self, session_id: str) -> Optional[Session]:
        """获取指定会话"""
        result = await self.db.execute(
            select(Session).where(Session.id == session_id)
        )
        return result.scalar_one_or_none()

    async def list_sessions(self, limit: Optional[int] = None, offset: int = 0) -> List[Session]:
        """列出所有会话，按更新时间倒序排列"""
        query = select(Session).order_by(Session.updated_at.desc())
        
        if limit is not None:
            query = query.limit(limit).offset(offset)
            
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_session(self, session_id: str, name: Optional[str] = None) -> Optional[Session]:
        """更新会话信息"""
        session = await self.get_session(session_id)
        if session is None:
            return None
            
        if name is not None:
            session.name = name
        session.updated_at = datetime.now(timezone.utc)
        
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def delete_session(self, session_id: str) -> bool:
        """删除会话及其关联的工具调用记录"""
        from sqlalchemy import delete
        from backend.models.tool_conversation import ToolConversation
        from loguru import logger
        from backend.modules.session.context_service import (
            reset_conversation_context_runtime_state,
        )
        
        session = await self.get_session(session_id)
        if session is None:
            return False
        
        # 1. 删除工具调用记录
        tool_conv_result = await self.db.execute(
            delete(ToolConversation).where(ToolConversation.session_id == session_id)
        )
        deleted_tool_convs = tool_conv_result.rowcount
        
        # 2. 删除会话（消息会自动级联删除）
        await self.db.delete(session)
        await self.db.commit()
        reset_conversation_context_runtime_state(session_id)
        
        logger.info(f"Deleted session {session_id} with {deleted_tool_convs} tool conversations")
        return True

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        message_context: Optional[str] = None,
    ) -> Optional[Message]:
        """添加消息到会话"""
        session = await self.get_session(session_id)
        if session is None:
            return None
            
        if role not in ('user', 'assistant', 'system'):
            raise ValueError(f"Invalid role: {role}. Must be 'user', 'assistant', or 'system'")
        
        message = Message(
            session_id=session_id,
            role=role,
            content=content,
            message_context=message_context,
            created_at=datetime.now(timezone.utc)
        )
        self.db.add(message)
        session.updated_at = datetime.now(timezone.utc)
        
        await self.db.commit()
        await self.db.refresh(message)
        return message

    async def get_messages(
        self,
        session_id: str,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> List[Message]:
        """获取会话的消息列表，按创建时间正序排列
        
        Args:
            session_id: 会话ID
            limit: 限制返回的消息数量（从最新的消息开始计数）
            offset: 偏移量
            
        Returns:
            消息列表（按时间正序）
        """
        if limit is not None:
            # 如果指定了limit，先获取最新的N条消息，然后按时间正序返回
            # 这样可以确保返回的是最近的对话
            query = (
                select(Message)
                .where(Message.session_id == session_id)
                .order_by(Message.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            result = await self.db.execute(query)
            messages = list(result.scalars().all())
            # 反转列表，使其按时间正序
            return list(reversed(messages))
        else:
            # 没有limit时，直接按时间正序返回所有消息
            query = (
                select(Message)
                .where(Message.session_id == session_id)
                .order_by(Message.created_at.asc())
                .offset(offset)
            )
            result = await self.db.execute(query)
            return list(result.scalars().all())

    async def get_session_with_messages(self, session_id: str) -> Optional[Session]:
        """获取会话及其所有消息"""
        result = await self.db.execute(
            select(Session)
            .where(Session.id == session_id)
            .options(selectinload(Session.messages))
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _reset_context_tracking(session: Session) -> None:
        """在删除/清空消息后重置上下文压缩状态。"""
        session.last_summarized_msg_id = None
        session.auto_memory_summary_msg_id = None
        session.short_context_summary = None
        session.short_context_summary_msg_id = None
        session.short_context_summary_updated_at = None
        session.short_context_summary_window_size = None

    async def clear_messages(self, session_id: str) -> bool:
        """清空会话的所有消息及其关联的工具调用记录"""
        from sqlalchemy import delete
        from backend.models.tool_conversation import ToolConversation
        from loguru import logger
        from backend.modules.session.context_service import (
            reset_conversation_context_runtime_state,
        )
        
        session = await self.get_session(session_id)
        if session is None:
            return False
        
        # 1. 获取该会话的所有消息 ID
        messages = await self.get_messages(session_id=session_id)
        message_ids = [msg.id for msg in messages]
        
        # 2. 删除这些消息关联的工具调用记录
        if message_ids:
            tool_conv_result = await self.db.execute(
                delete(ToolConversation).where(ToolConversation.message_id.in_(message_ids))
            )
            deleted_tool_convs = tool_conv_result.rowcount
            logger.info(f"Deleted {deleted_tool_convs} tool conversations for session {session_id}")
        
        # 3. 删除消息
        await self.db.execute(
            delete(Message).where(Message.session_id == session_id)
        )
        self._reset_context_tracking(session)
        session.updated_at = datetime.now(timezone.utc)
        
        await self.db.commit()
        reset_conversation_context_runtime_state(session_id)
        return True

    async def delete_message(self, message_id: int) -> bool:
        """删除单条消息及其关联的工具调用记录
        
        Args:
            message_id: 消息 ID
            
        Returns:
            bool: 是否成功删除
        """
        from sqlalchemy import delete
        from backend.models.tool_conversation import ToolConversation
        from loguru import logger
        from backend.modules.session.context_service import (
            reset_conversation_context_runtime_state,
        )
        
        result = await self.db.execute(
            select(Message).where(Message.id == message_id)
        )
        message = result.scalar_one_or_none()
        
        if message is None:
            return False
        
        session_id = message.session_id
        
        # 1. 删除工具调用记录
        tool_conv_result = await self.db.execute(
            delete(ToolConversation).where(ToolConversation.message_id == message_id)
        )
        deleted_tool_convs = tool_conv_result.rowcount
        
        # 2. 删除消息
        await self.db.delete(message)
        
        # 3. 更新会话时间戳
        session = await self.get_session(session_id)
        if session:
            self._reset_context_tracking(session)
            session.updated_at = datetime.now(timezone.utc)
        
        await self.db.commit()
        reset_conversation_context_runtime_state(session_id)
        
        logger.info(f"Deleted message {message_id} with {deleted_tool_convs} tool conversations")
        return True

    async def get_message_count(self, session_id: str) -> int:
        """获取会话的消息数量"""
        from sqlalchemy import func
        
        result = await self.db.execute(
            select(func.count(Message.id)).where(Message.session_id == session_id)
        )
        return result.scalar() or 0

