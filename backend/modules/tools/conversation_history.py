"""工具调用对话历史记录模块

记录 AI 模型与工具之间的完整对话历史，包括：
- 工具调用请求（AI 发起）
- 工具执行结果（工具返回）
- 时间戳、会话信息等

支持两种存储模式：
1. 内存模式：使用 deque，最多保留 50 条记录（默认）
2. 数据库模式：持久化存储，支持查询和统计
"""

from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict
import json
from loguru import logger


@dataclass
class ToolConversation:
    """工具调用对话记录"""
    
    id: str  # 唯一标识
    session_id: str  # 会话 ID
    timestamp: str  # 时间戳（ISO 格式）
    tool_name: str  # 工具名称
    arguments: Dict[str, Any]  # 工具参数
    message_id: Optional[int] = None  # 关联的消息ID
    user_message: Optional[str] = None  # 触发工具调用的用户消息
    result: Optional[str] = None  # 工具执行结果
    error: Optional[str] = None  # 错误信息（如果有）
    duration_ms: Optional[int] = None  # 执行耗时（毫秒）
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)


class ToolConversationHistory:
    """工具调用对话历史管理器
    
    支持两种存储模式：
    1. 内存模式（use_db=False）：使用 deque，最多保留 max_size 条记录
    2. 数据库模式（use_db=True）：持久化存储到数据库
    """
    
    def __init__(self, max_size: int = 50, use_db: bool = False):
        """初始化
        
        Args:
            max_size: 内存模式下的最大记录数，默认 50
            use_db: 是否使用数据库存储，默认 False（内存模式）
        """
        self.max_size = max_size
        self.use_db = use_db
        self._history: deque[ToolConversation] = deque(maxlen=max_size)
        self._counter = 0  # 用于生成唯一 ID
        
        if use_db:
            logger.debug("工具对话历史使用数据库模式")
        else:
            logger.debug(f"工具对话历史使用内存模式（最多 {max_size} 条）")
    
    def add_conversation(
        self,
        session_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
        message_id: Optional[int] = None,
        user_message: Optional[str] = None,
        result: Optional[str] = None,
        error: Optional[str] = None,
        duration_ms: Optional[int] = None
    ) -> str:
        """添加一条工具调用对话记录
        
        Args:
            session_id: 会话 ID
            tool_name: 工具名称
            arguments: 工具参数
            message_id: 关联的消息ID
            user_message: 触发工具调用的用户消息
            result: 工具执行结果
            error: 错误信息
            duration_ms: 执行耗时（毫秒）
            
        Returns:
            记录的唯一 ID
        """
        self._counter += 1
        conversation_id = f"conv_{self._counter}_{int(datetime.now().timestamp() * 1000)}"
        
        conversation = ToolConversation(
            id=conversation_id,
            session_id=session_id,
            timestamp=datetime.now().isoformat(),
            tool_name=tool_name,
            arguments=arguments,
            message_id=message_id,
            user_message=user_message,
            result=result,
            error=error,
            duration_ms=duration_ms
        )
        
        # 内存存储
        self._history.append(conversation)
        
        # 数据库存储（异步）
        if self.use_db:
            try:
                import asyncio
                asyncio.create_task(self._save_to_db(conversation))
            except Exception as e:
                logger.warning(f"Failed to save conversation to database: {e}")
        
        return conversation_id
    
    async def _save_to_db(self, conversation: ToolConversation):
        """保存对话记录到数据库，并自动清理超过限制的旧记录
        
        Args:
            conversation: 对话记录
        """
        try:
            from backend.database import get_db
            from backend.models.tool_conversation import ToolConversation as DBToolConversation
            from sqlalchemy import select, func, delete
            
            async for db in get_db():
                # 1. 保存新记录
                db_conv = DBToolConversation(
                    id=conversation.id,
                    session_id=conversation.session_id,
                    message_id=conversation.message_id,
                    timestamp=conversation.timestamp,
                    tool_name=conversation.tool_name,
                    arguments=json.dumps(conversation.arguments),
                    user_message=conversation.user_message,
                    result=conversation.result,
                    error=conversation.error,
                    duration_ms=conversation.duration_ms,
                )
                
                db.add(db_conv)
                await db.commit()
                
                # 2. 检查总记录数
                count_query = select(func.count()).select_from(DBToolConversation)
                result = await db.execute(count_query)
                total_count = result.scalar()
                
                # 3. 如果超过 200 条，删除最旧的记录
                max_records = 200
                if total_count > max_records:
                    records_to_delete = total_count - max_records
                    logger.info(f"工具对话历史超过 {max_records} 条，删除最旧的 {records_to_delete} 条记录")
                    
                    # 获取最旧的记录 ID
                    oldest_query = select(DBToolConversation.id).order_by(
                        DBToolConversation.timestamp.asc()
                    ).limit(records_to_delete)
                    oldest_result = await db.execute(oldest_query)
                    oldest_ids = [row[0] for row in oldest_result.fetchall()]
                    
                    # 删除最旧的记录
                    if oldest_ids:
                        delete_query = delete(DBToolConversation).where(
                            DBToolConversation.id.in_(oldest_ids)
                        )
                        await db.execute(delete_query)
                        await db.commit()
                        logger.info(f"已删除 {len(oldest_ids)} 条最旧的工具对话记录")
                
                break
                
        except Exception as e:
            logger.error(f"Failed to save conversation to database: {e}")
    
    async def get_all(self, limit: Optional[int] = None, offset: int = 0) -> List[Dict[str, Any]]:
        """获取所有对话记录（从新到旧）
        
        Args:
            limit: 限制返回数量（可选）
            offset: 偏移量，用于分页（默认0）
            
        Returns:
            对话记录列表
        """
        if self.use_db:
            # 从数据库读取
            try:
                return await self._get_all_from_db(limit, offset)
            except Exception as e:
                logger.error(f"Failed to get conversations from database: {e}")
                # 降级到内存模式
                pass
        
        # 从内存读取
        conversations = list(reversed(self._history))
        if offset:
            conversations = conversations[offset:]
        if limit:
            conversations = conversations[:limit]
        return [conv.to_dict() for conv in conversations]
    
    async def _get_all_from_db(self, limit: Optional[int] = None, offset: int = 0) -> List[Dict[str, Any]]:
        """从数据库获取所有对话记录
        
        Args:
            limit: 限制返回数量
            offset: 偏移量，用于分页
            
        Returns:
            对话记录列表
        """
        from backend.database import get_db
        from backend.models.tool_conversation import ToolConversation as DBToolConversation
        from sqlalchemy import select
        
        async for db in get_db():
            query = select(DBToolConversation).order_by(DBToolConversation.timestamp.asc())
            if offset:
                query = query.offset(offset)
            if limit:
                query = query.limit(limit)
            
            result = await db.execute(query)
            conversations = result.scalars().all()
            
            return [conv.to_dict() for conv in conversations]
        
        return []
    
    async def get_by_session(self, session_id: str, limit: Optional[int] = None, offset: int = 0) -> List[Dict[str, Any]]:
        """获取指定会话的对话记录
        
        Args:
            session_id: 会话 ID
            limit: 限制返回数量（可选）
            offset: 偏移量，用于分页（默认0）
            
        Returns:
            对话记录列表
        """
        if self.use_db:
            try:
                return await self._get_by_session_from_db(session_id, limit, offset)
            except Exception as e:
                logger.error(f"Failed to get conversations from database: {e}")
        
        conversations = [
            conv.to_dict()
            for conv in reversed(self._history)
            if conv.session_id == session_id
        ]
        if offset:
            conversations = conversations[offset:]
        if limit:
            conversations = conversations[:limit]
        return conversations
    
    async def _get_by_session_from_db(self, session_id: str, limit: Optional[int] = None, offset: int = 0) -> List[Dict[str, Any]]:
        """从数据库获取指定会话的对话记录"""
        from backend.database import get_db
        from backend.models.tool_conversation import ToolConversation as DBToolConversation
        from sqlalchemy import select
        
        async for db in get_db():
            query = select(DBToolConversation).where(
                DBToolConversation.session_id == session_id
            ).order_by(DBToolConversation.timestamp.asc())
            
            if offset:
                query = query.offset(offset)
            if limit:
                query = query.limit(limit)
            
            result = await db.execute(query)
            conversations = result.scalars().all()
            
            return [conv.to_dict() for conv in conversations]
        
        return []
    
    async def get_by_tool(self, tool_name: str, limit: Optional[int] = None, offset: int = 0) -> List[Dict[str, Any]]:
        """获取指定工具的对话记录
        
        Args:
            tool_name: 工具名称
            limit: 限制返回数量（可选）
            offset: 偏移量，用于分页（默认0）
            
        Returns:
            对话记录列表
        """
        if self.use_db:
            try:
                return await self._get_by_tool_from_db(tool_name, limit, offset)
            except Exception as e:
                logger.error(f"Failed to get conversations from database: {e}")
        
        conversations = [
            conv.to_dict()
            for conv in reversed(self._history)
            if conv.tool_name == tool_name
        ]
        if offset:
            conversations = conversations[offset:]
        if limit:
            conversations = conversations[:limit]
        return conversations
    
    async def _get_by_tool_from_db(self, tool_name: str, limit: Optional[int] = None, offset: int = 0) -> List[Dict[str, Any]]:
        """从数据库获取指定工具的对话记录"""
        from backend.database import get_db
        from backend.models.tool_conversation import ToolConversation as DBToolConversation
        from sqlalchemy import select
        
        async for db in get_db():
            query = select(DBToolConversation).where(
                DBToolConversation.tool_name == tool_name
            ).order_by(DBToolConversation.timestamp.asc())
            
            if offset:
                query = query.offset(offset)
            if limit:
                query = query.limit(limit)
            
            result = await db.execute(query)
            conversations = result.scalars().all()
            
            return [conv.to_dict() for conv in conversations]
        
        return []
    
    def get_recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近的 N 条对话记录
        
        Args:
            limit: 记录数量
            
        Returns:
            对话记录列表
        """
        recent = list(reversed(self._history))[:limit]
        return [conv.to_dict() for conv in recent]
    
    def clear(self) -> None:
        """清空所有对话记录"""
        self._history.clear()
        self._counter = 0
        
        if self.use_db:
            try:
                import asyncio
                asyncio.create_task(self._clear_db())
            except Exception as e:
                logger.warning(f"Failed to clear database: {e}")
    
    async def backfill_message_id(self, session_id: str, message_id: int) -> int:
        """回填 message_id 到该会话中所有未关联的工具调用记录
        
        在 assistant 消息保存到数据库后调用，将该轮对话产生的工具调用
        关联到对应的 assistant 消息。
        
        Args:
            session_id: 会话 ID
            message_id: assistant 消息的数据库 ID
            
        Returns:
            更新的记录数
        """
        # 更新内存中的记录
        updated = 0
        for conv in self._history:
            if conv.session_id == session_id and conv.message_id is None:
                conv.message_id = message_id
                updated += 1
        
        # 更新数据库中的记录
        if self.use_db:
            try:
                updated = await self._backfill_message_id_in_db(session_id, message_id)
            except Exception as e:
                logger.error(f"Failed to backfill message_id in database: {e}")
        
        if updated > 0:
            logger.info(f"Backfilled message_id={message_id} to {updated} tool conversations")
        
        return updated
    
    async def _backfill_message_id_in_db(self, session_id: str, message_id: int) -> int:
        """在数据库中回填 message_id"""
        from backend.database import get_db
        from backend.models.tool_conversation import ToolConversation as DBToolConversation
        from sqlalchemy import update
        
        async for db in get_db():
            stmt = (
                update(DBToolConversation)
                .where(
                    DBToolConversation.session_id == session_id,
                    DBToolConversation.message_id.is_(None)
                )
                .values(message_id=message_id)
            )
            result = await db.execute(stmt)
            await db.commit()
            return result.rowcount
        
        return 0
    
    async def _clear_db(self):
        """清空数据库中的对话记录"""
        try:
            from backend.database import get_db
            from backend.models.tool_conversation import ToolConversation as DBToolConversation
            from sqlalchemy import delete
            
            async for db in get_db():
                await db.execute(delete(DBToolConversation))
                await db.commit()
                break
                
        except Exception as e:
            logger.error(f"Failed to clear database: {e}")
    
    async def get_stats(self) -> Dict[str, Any]:
        """获取统计信息
        
        Returns:
            统计信息字典
        """
        if self.use_db:
            try:
                return await self._get_stats_from_db()
            except Exception as e:
                logger.error(f"Failed to get stats from database: {e}")
        
        if not self._history:
            return {
                "total": 0,
                "by_tool": {},
                "by_session": {},
                "success_rate": 0.0
            }
        
        # 按工具统计
        by_tool: Dict[str, int] = {}
        for conv in self._history:
            by_tool[conv.tool_name] = by_tool.get(conv.tool_name, 0) + 1
        
        # 按会话统计
        by_session: Dict[str, int] = {}
        for conv in self._history:
            by_session[conv.session_id] = by_session.get(conv.session_id, 0) + 1
        
        # 成功率
        success_count = sum(1 for conv in self._history if conv.error is None)
        success_rate = success_count / len(self._history) * 100
        
        return {
            "total": len(self._history),
            "by_tool": by_tool,
            "by_session": by_session,
            "success_rate": round(success_rate, 2)
        }
    
    async def _get_stats_from_db(self) -> Dict[str, Any]:
        """从数据库获取统计信息"""
        from backend.database import get_db
        from backend.models.tool_conversation import ToolConversation as DBToolConversation
        from sqlalchemy import select, func
        
        async for db in get_db():
            # 总数
            total_result = await db.execute(select(func.count(DBToolConversation.id)))
            total = total_result.scalar() or 0
            
            if total == 0:
                return {
                    "total": 0,
                    "by_tool": {},
                    "by_session": {},
                    "success_rate": 0.0
                }
            
            # 按工具统计
            tool_result = await db.execute(
                select(DBToolConversation.tool_name, func.count(DBToolConversation.id))
                .group_by(DBToolConversation.tool_name)
            )
            by_tool = {row[0]: row[1] for row in tool_result}
            
            # 按会话统计
            session_result = await db.execute(
                select(DBToolConversation.session_id, func.count(DBToolConversation.id))
                .group_by(DBToolConversation.session_id)
            )
            by_session = {row[0]: row[1] for row in session_result}
            
            # 成功率
            success_result = await db.execute(
                select(func.count(DBToolConversation.id))
                .where(DBToolConversation.error.is_(None))
            )
            success_count = success_result.scalar() or 0
            success_rate = (success_count / total * 100) if total > 0 else 0.0
            
            return {
                "total": total,
                "by_tool": by_tool,
                "by_session": by_session,
                "success_rate": round(success_rate, 2)
            }
        
        return {
            "total": 0,
            "by_tool": {},
            "by_session": {},
            "success_rate": 0.0
        }


# 全局单例 - 默认使用数据库模式
_conversation_history = ToolConversationHistory(max_size=50, use_db=True)


def get_conversation_history() -> ToolConversationHistory:
    """获取全局工具调用对话历史管理器"""
    return _conversation_history
