"""会话管理器"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models.message import Message
from backend.models.session import Session


class SessionManager:
    """会话管理器 - 负责会话的 CRUD 操作、消息管理和会话持久化"""

    def __init__(self, db: AsyncSession, summarizer=None):
        self.db = db
        self.summarizer = summarizer
        self.conversation_summary = ""

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

    async def list_sessions(self, limit: Optional[int] = None, offset: int = 0) -> list[Session]:
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
        """删除会话"""
        session = await self.get_session(session_id)
        if session is None:
            return False
            
        await self.db.delete(session)
        await self.db.commit()
        return True

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str
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
    ) -> list[Message]:
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

    async def clear_messages(self, session_id: str) -> bool:
        """清空会话的所有消息"""
        from sqlalchemy import delete
        
        session = await self.get_session(session_id)
        if session is None:
            return False
            
        await self.db.execute(
            delete(Message).where(Message.session_id == session_id)
        )
        session.updated_at = datetime.now(timezone.utc)
        
        await self.db.commit()
        return True

    async def get_message_count(self, session_id: str) -> int:
        """获取会话的消息数量"""
        from sqlalchemy import func
        
        result = await self.db.execute(
            select(func.count(Message.id)).where(Message.session_id == session_id)
        )
        return result.scalar() or 0

    async def get_history_with_summary(
        self,
        session_id: str,
        limit: Optional[int] = 50
    ) -> list[dict]:
        """获取带总结的对话历史（短期记忆优化）"""
        messages = await self.get_messages(session_id=session_id, limit=limit)

        message_dicts = [
            {
                "role": msg.role,
                "content": msg.content,
            }
            for msg in messages
        ]

        if not self.summarizer or len(message_dicts) <= 15:
            return message_dicts

        if self.summarizer.should_summarize(message_dicts):
            to_summarize, to_keep = self.summarizer.get_messages_to_keep(
                message_dicts,
                keep_recent=10
            )

            self.conversation_summary = await self.summarizer.summarize_conversation(
                messages=to_summarize,
                previous_summary=self.conversation_summary
            )

            summary_message = {
                "role": "system",
                "content": f"## Previous Conversation Summary\n\n{self.conversation_summary}"
            }

            return [summary_message] + to_keep

        return message_dicts

    async def summarize_overflow(
        self,
        session_id: str,
        max_history: int,
        provider=None,
        model: str | None = None,
        memory_store=None,
    ) -> None:
        """滚动窗口溢出总结：将超出 max_history 的旧消息总结写入 MEMORY.md。

        在加载历史之前调用。只总结尚未总结过的溢出消息（通过 Session.last_summarized_msg_id 跟踪）。

        Args:
            session_id: 会话 ID
            max_history: 最大保留消息数
            provider: LLM provider（用于生成总结）
            model: 模型名称
            memory_store: MemoryStore 实例（写入记忆）
        """
        if not provider or not memory_store:
            return
        if max_history <= 0:
            return

        from sqlalchemy import func

        try:
            # 获取总消息数
            total_count = await self.get_message_count(session_id)
            if total_count <= max_history:
                return  # 没有溢出

            overflow_count = total_count - max_history

            # 获取 session 的 last_summarized_msg_id
            session = await self.get_session(session_id)
            if session is None:
                return

            last_summarized_id = session.last_summarized_msg_id or 0

            # 查询溢出的、尚未总结的消息
            query = (
                select(Message)
                .where(Message.session_id == session_id)
                .where(Message.id > last_summarized_id)
                .order_by(Message.created_at.asc())
                .limit(overflow_count)
            )
            result = await self.db.execute(query)
            overflow_messages = list(result.scalars().all())

            if not overflow_messages:
                return

            # 过滤：只总结 user/assistant 消息
            to_summarize = [
                {"role": msg.role, "content": msg.content}
                for msg in overflow_messages
                if msg.role in ("user", "assistant") and msg.content
            ]

            if len(to_summarize) < 3:
                # 太少不值得总结，但仍更新标记
                session.last_summarized_msg_id = overflow_messages[-1].id
                await self.db.commit()
                return

            # 用 LLM 生成总结
            from backend.modules.agent.analyzer import MessageAnalyzer
            from backend.modules.agent.prompts import OVERFLOW_SUMMARY_PROMPT

            analyzer = MessageAnalyzer()
            formatted = analyzer.format_messages_for_summary(to_summarize, max_chars=4000)
            prompt = OVERFLOW_SUMMARY_PROMPT.format(messages=formatted)

            summary_parts = []
            async for chunk in provider.chat_stream(
                messages=[{"role": "user", "content": prompt}],
                model=model,
                temperature=0.3,
            ):
                if chunk.is_content and chunk.content:
                    summary_parts.append(chunk.content)

            summary = "".join(summary_parts).strip()

            if summary and "无需记录" not in summary:
                memory_store.append_entry(source="auto-overflow", content=summary)
                from loguru import logger
                logger.info(
                    f"Overflow summary saved for session {session_id}: "
                    f"{len(overflow_messages)} msgs -> memory"
                )

            # 更新标记
            session.last_summarized_msg_id = overflow_messages[-1].id
            await self.db.commit()

        except Exception as e:
            from loguru import logger
            logger.error(f"Overflow summarize failed for session {session_id}: {e}")

