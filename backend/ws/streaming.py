"""WebSocket 流式响应推送

提供流式响应的高级功能：
- 流式消息推送
- 进度跟踪
- 速率控制
- 缓冲管理
"""

import asyncio
from typing import AsyncIterator, Callable

from loguru import logger

from backend.ws.connection import send_message_chunk


# ============================================================================
# Streaming Response Handler
# ============================================================================


class StreamingResponseHandler:
    """流式响应处理器

    管理流式响应的推送，支持：
    - 自动分块
    - 进度跟踪
    - 速率控制
    - 错误处理
    """

    def __init__(
        self,
        session_id: str,
        chunk_size: int = 50,
        delay_ms: int = 0,
        on_progress: Callable[[int, int], None] | None = None,
    ):
        """初始化流式响应处理器

        Args:
            session_id: 会话 ID
            chunk_size: 每个块的字符数（0 表示不分块）
            delay_ms: 每个块之间的延迟（毫秒）
            on_progress: 进度回调函数 (current, total)
        """
        self.session_id = session_id
        self.chunk_size = chunk_size
        self.delay_ms = delay_ms
        self.on_progress = on_progress

        self.total_sent = 0
        self.chunk_count = 0

    async def stream_text(self, text: str) -> int:
        """流式推送文本

        Args:
            text: 要推送的文本

        Returns:
            int: 发送的块数
        """
        if not text:
            return 0

        total_length = len(text)
        sent_count = 0

        if self.chunk_size > 0:
            # 分块发送
            for i in range(0, total_length, self.chunk_size):
                chunk = text[i : i + self.chunk_size]
                count = await send_message_chunk(self.session_id, chunk)

                if count > 0:
                    sent_count += 1
                    self.total_sent += len(chunk)
                    self.chunk_count += 1

                    # 调用进度回调
                    if self.on_progress:
                        self.on_progress(self.total_sent, total_length)

                    # 延迟
                    if self.delay_ms > 0:
                        await asyncio.sleep(self.delay_ms / 1000.0)
        else:
            # 一次性发送
            count = await send_message_chunk(self.session_id, text)
            if count > 0:
                sent_count = 1
                self.total_sent += len(text)
                self.chunk_count += 1

        return sent_count

    async def stream_iterator(
        self, iterator: AsyncIterator[str]
    ) -> int:
        """流式推送迭代器内容

        Args:
            iterator: 异步迭代器

        Returns:
            int: 发送的块数
        """
        sent_count = 0

        async for chunk in iterator:
            if chunk:
                count = await send_message_chunk(self.session_id, chunk)
                if count > 0:
                    sent_count += 1
                    self.total_sent += len(chunk)
                    self.chunk_count += 1

                    # 延迟
                    if self.delay_ms > 0:
                        await asyncio.sleep(self.delay_ms / 1000.0)

        return sent_count

    def get_stats(self) -> dict[str, int]:
        """获取统计信息

        Returns:
            dict: 统计信息
        """
        return {
            "total_sent": self.total_sent,
            "chunk_count": self.chunk_count,
        }


# ============================================================================
# Buffered Streaming
# ============================================================================


class BufferedStreamingHandler:
    """缓冲流式响应处理器

    使用缓冲区来优化小块的发送，减少网络开销。
    """

    def __init__(
        self,
        session_id: str,
        buffer_size: int = 100,
        flush_interval_ms: int = 100,
    ):
        """初始化缓冲流式响应处理器

        Args:
            session_id: 会话 ID
            buffer_size: 缓冲区大小（字符数）
            flush_interval_ms: 自动刷新间隔（毫秒）
        """
        self.session_id = session_id
        self.buffer_size = buffer_size
        self.flush_interval_ms = flush_interval_ms

        self.buffer = ""
        self.total_sent = 0
        self.flush_count = 0
        self._last_flush = asyncio.get_event_loop().time()

    async def write(self, text: str) -> None:
        """写入文本到缓冲区

        Args:
            text: 要写入的文本
        """
        self.buffer += text

        # 检查是否需要刷新
        current_time = asyncio.get_event_loop().time()
        time_since_flush = (current_time - self._last_flush) * 1000

        if (
            len(self.buffer) >= self.buffer_size
            or time_since_flush >= self.flush_interval_ms
        ):
            await self.flush()

    async def flush(self) -> int:
        """刷新缓冲区

        Returns:
            int: 发送的连接数
        """
        if not self.buffer:
            return 0

        count = await send_message_chunk(self.session_id, self.buffer)

        if count > 0:
            self.total_sent += len(self.buffer)
            self.flush_count += 1

        self.buffer = ""
        self._last_flush = asyncio.get_event_loop().time()

        return count

    async def stream_iterator(
        self, iterator: AsyncIterator[str]
    ) -> None:
        """流式推送迭代器内容（使用缓冲）

        Args:
            iterator: 异步迭代器
        """
        async for chunk in iterator:
            if chunk:
                await self.write(chunk)

        # 确保刷新剩余内容
        await self.flush()

    def get_stats(self) -> dict[str, int]:
        """获取统计信息

        Returns:
            dict: 统计信息
        """
        return {
            "total_sent": self.total_sent,
            "flush_count": self.flush_count,
            "buffer_length": len(self.buffer),
        }


# ============================================================================
# Helper Functions
# ============================================================================


async def stream_response(
    session_id: str,
    iterator: AsyncIterator[str],
    use_buffer: bool = True,
    buffer_size: int = 100,
) -> dict[str, int]:
    """流式推送响应（便捷函数）

    Args:
        session_id: 会话 ID
        iterator: 异步迭代器
        use_buffer: 是否使用缓冲
        buffer_size: 缓冲区大小

    Returns:
        dict: 统计信息
    """
    if use_buffer:
        handler = BufferedStreamingHandler(
            session_id=session_id,
            buffer_size=buffer_size,
        )
        await handler.stream_iterator(iterator)
        return handler.get_stats()
    else:
        handler = StreamingResponseHandler(session_id=session_id)
        await handler.stream_iterator(iterator)
        return handler.get_stats()


async def stream_text(
    session_id: str,
    text: str,
    chunk_size: int = 50,
    delay_ms: int = 0,
) -> dict[str, int]:
    """流式推送文本（便捷函数）

    Args:
        session_id: 会话 ID
        text: 要推送的文本
        chunk_size: 每个块的字符数
        delay_ms: 每个块之间的延迟（毫秒）

    Returns:
        dict: 统计信息
    """
    handler = StreamingResponseHandler(
        session_id=session_id,
        chunk_size=chunk_size,
        delay_ms=delay_ms,
    )
    await handler.stream_text(text)
    return handler.get_stats()
