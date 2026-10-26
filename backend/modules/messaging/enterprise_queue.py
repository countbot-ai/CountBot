"""企业级消息队列：四级优先级调度、内容哈希去重、死信队列与可选持久化，失败消息最多重试 3 次并降级优先级。"""

import asyncio
import hashlib
import json
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from loguru import logger

from backend.modules.channels.base import InboundMessage


class MessagePriority(Enum):
    """消息优先级枚举，数值越大优先级越高。"""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    URGENT = 3


@dataclass
class QueuedMessage:
    """队列消息包装器：封装原始消息及其队列元数据。
    
    Attributes:
        id: 消息唯一标识符（UUID）
        message: 原始入站消息
        priority: 消息优先级
        timestamp: 入队时间戳
        retry_count: 当前重试次数
        max_retries: 最大重试次数
    """
    id: str
    message: InboundMessage
    priority: MessagePriority
    timestamp: float
    retry_count: int = 0
    max_retries: int = 3
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'id': self.id,
            'message': {
                'channel': self.message.channel,
                'chat_id': self.message.chat_id,
                'sender_id': self.message.sender_id,
                'content': self.message.content,
                'metadata': self.message.metadata,
            },
            'priority': self.priority.name,
            'timestamp': self.timestamp,
            'retry_count': self.retry_count,
            'max_retries': self.max_retries,
        }


class EnterpriseMessageQueue:
    """企业级消息队列：优先级调度、内容哈希去重、死信处理与可选持久化。
    
    Attributes:
        _queues: 优先级队列映射
        _outbound: 出站消息队列
        _dead_letter_queue: 死信队列
        _message_hashes: 消息去重哈希表
        _metrics: 监控指标
    """
    
    def __init__(
        self,
        persist_dir: Optional[Path] = None,
        enable_persistence: bool = False,
        enable_dedup: bool = True,
        dedup_window: int = 60,
    ):
        # 优先级队列（入站）
        self._queues = {
            MessagePriority.URGENT: asyncio.Queue(),
            MessagePriority.HIGH: asyncio.Queue(),
            MessagePriority.NORMAL: asyncio.Queue(),
            MessagePriority.LOW: asyncio.Queue(),
        }
        
        # 出站队列
        self._outbound: asyncio.Queue = asyncio.Queue()
        
        # 死信队列
        self._dead_letter_queue = asyncio.Queue()
        
        # 消息去重
        self._message_hashes = {}  # {hash: timestamp}
        self._dedup_checks = 0
        self._dedup_enabled = enable_dedup
        self._dedup_window = dedup_window
        
        # 持久化
        self._persist_dir = persist_dir
        self._persistence_enabled = enable_persistence
        if enable_persistence and persist_dir:
            persist_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Message persistence enabled: {persist_dir}")
        
        # 监控指标
        self._metrics = {
            'total_received': 0,
            'total_processed': 0,
            'total_failed': 0,
            'total_duplicates': 0,
        }
        
        logger.debug("EnterpriseMessageQueue initialized")
    
    async def enqueue(
        self,
        message: InboundMessage,
        priority: MessagePriority = MessagePriority.NORMAL
    ) -> bool:
        """入队消息"""
        # 消息去重
        if self._dedup_enabled:
            msg_hash = self._hash_message(message)
            if self._is_duplicate(msg_hash):
                self._metrics['total_duplicates'] += 1
                logger.warning(f"Duplicate message dropped (hash={msg_hash[:8]}, channel={message.channel}, sender={message.sender_id}, content={message.content[:30]}...)")
                return False
            self._message_hashes[msg_hash] = time.time()
        
        queued_msg = QueuedMessage(
            id=str(uuid.uuid4()),
            message=message,
            priority=priority,
            timestamp=time.time(),
        )
        
        # 持久化
        if self._persistence_enabled:
            await self._persist_message(queued_msg)
        
        await self._queues[priority].put(queued_msg)
        self._metrics['total_received'] += 1
        
        logger.debug(f"Message enqueued: {queued_msg.id[:8]} (priority: {priority.name})")
        return True
    
    async def dequeue(self) -> QueuedMessage:
        """出队消息（按优先级）"""
        for priority in [
            MessagePriority.URGENT,
            MessagePriority.HIGH,
            MessagePriority.NORMAL,
            MessagePriority.LOW,
        ]:
            queue = self._queues[priority]
            if not queue.empty():
                msg = await queue.get()
                logger.debug(f"Message dequeued: {msg.id[:8]} (priority: {priority.name})")
                return msg
        
        tasks = [
            asyncio.create_task(queue.get())
            for queue in self._queues.values()
        ]
        
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        
        for task in pending:
            task.cancel()
        
        msg = done.pop().result()
        logger.debug(f"Message dequeued (waited): {msg.id[:8]}")
        return msg
    
    async def publish_inbound(self, message: InboundMessage) -> None:
        """发布入站消息到队列"""
        priority = getattr(message, 'priority', MessagePriority.NORMAL)
        await self.enqueue(message, priority)
    
    async def consume_inbound(self) -> InboundMessage:
        """从队列消费入站消息"""
        queued_msg = await self.dequeue()
        return queued_msg.message
    
    async def publish_outbound(self, message) -> None:
        """发布出站消息"""
        await self._outbound.put(message)
        logger.debug(f"Outbound message published: {message.channel}/{message.chat_id}")
    
    async def consume_outbound(self):
        """消费出站消息（阻塞直到可用）"""
        return await self._outbound.get()
    
    async def mark_success(self, msg: QueuedMessage):
        """标记消息处理成功"""
        self._metrics['total_processed'] += 1
        
        if self._persistence_enabled:
            await self._delete_persisted_message(msg.id)
    
    async def mark_failed(self, msg: QueuedMessage, error: str):
        """标记消息处理失败"""
        msg.retry_count += 1
        
        if msg.retry_count < msg.max_retries:
            lower_priority = MessagePriority(max(0, msg.priority.value - 1))
            await self._queues[lower_priority].put(msg)
            logger.warning(f"Message retry {msg.retry_count}/{msg.max_retries}: {msg.id[:8]}")
        else:
            await self._dead_letter_queue.put((msg, error))
            self._metrics['total_failed'] += 1
            logger.error(f"Message moved to DLQ: {msg.id[:8]}, error: {error}")
    
    def _hash_message(self, msg: InboundMessage) -> str:
        """计算消息哈希；附件必须参与，否则同文案不同图片的消息会被误判为重复。"""
        media = getattr(msg, "media", None) or []
        media_signature = "|".join(str(item) for item in media)
        content = (
            f"{msg.channel}:{msg.chat_id}:{msg.sender_id}:{media_signature}:{msg.content}"
        )
        return hashlib.md5(content.encode()).hexdigest()
    
    # 每累计这么多次去重检查，执行一次全表清扫
    _DEDUP_SWEEP_INTERVAL = 512

    def _sweep_expired_hashes(self, now: float) -> None:
        """清理已过去重窗口的哈希条目：按需删除会让条目永久累积，故定期全表扫描。"""
        expired = [
            key
            for key, timestamp in self._message_hashes.items()
            if now - timestamp > self._dedup_window
        ]
        for key in expired:
            del self._message_hashes[key]

    def _is_duplicate(self, msg_hash: str) -> bool:
        """检查是否重复消息"""
        now = time.time()
        self._dedup_checks += 1
        if self._dedup_checks % self._DEDUP_SWEEP_INTERVAL == 0:
            self._sweep_expired_hashes(now)

        if msg_hash not in self._message_hashes:
            return False

        timestamp = self._message_hashes[msg_hash]
        if now - timestamp > self._dedup_window:
            del self._message_hashes[msg_hash]
            return False

        return True
    
    async def _persist_message(self, msg: QueuedMessage):
        """持久化消息"""
        if not self._persist_dir:
            return
        
        try:
            file_path = self._persist_dir / f"{msg.id}.json"
            data = msg.to_dict()
            file_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.error(f"Failed to persist message: {e}")
    
    async def _delete_persisted_message(self, msg_id: str):
        """删除持久化消息"""
        if not self._persist_dir:
            return
        
        try:
            file_path = self._persist_dir / f"{msg_id}.json"
            if file_path.exists():
                file_path.unlink()
        except Exception as e:
            logger.error(f"Failed to delete persisted message: {e}")
    
    def get_metrics(self) -> dict:
        """获取监控指标"""
        metrics = self._metrics.copy()
        metrics['queue_sizes'] = {
            priority.name: queue.qsize()
            for priority, queue in self._queues.items()
        }
        metrics['dead_letter_size'] = self._dead_letter_queue.qsize()
        return metrics
    
    def get_queue_size(self) -> int:
        """获取总队列大小"""
        return sum(q.qsize() for q in self._queues.values())

    
    @property
    def inbound_size(self) -> int:
        """获取入站队列总大小"""
        return self.get_queue_size()
    
    @property
    def outbound_size(self) -> int:
        """获取出站队列大小"""
        return self._outbound.qsize()
