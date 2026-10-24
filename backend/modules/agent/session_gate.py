"""会话级执行闸门：同一会话同一时刻只允许一轮 Agent 处理。

WebSocket 与 IM 渠道都可能对同一会话并发发起处理：IM 消费到消息后直接
create_task，工具执行期间再来一条消息就会并发进入 Agent 循环；WebSocket
单连接内串行，但同一会话被多个连接（多端登录、刷新后旧连接未断）订阅时
同样并发。两条链路共用这里的同一个闸门实例，先到者执行，后到者按到达
顺序等待，不丢消息、不交错。

命令类消息（/stop、/new 等）不经过本闸门，必须能在处理进行中立即生效。
"""

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from loguru import logger


@dataclass
class PendingMessage:
    """排队等待插入当前轮次的用户消息。

    ``consumed`` 是防止重复处理的关键：消息被正在执行的那一轮取走并插入上下文后
    置为 True，它自己随后获得执行权时据此直接跳过，避免同一条消息被回复两次。
    """

    text: str
    created_at: float = field(default_factory=time.monotonic)
    consumed: bool = False
    id: str = field(default_factory=lambda: uuid.uuid4().hex)


class SessionTurnGate:
    """按会话串行的准入闸门。

    每个会话一把 FIFO 锁：等待者按调用顺序获得执行权，保证消息处理顺序与
    用户发送顺序一致。
    """

    # 等待超过该秒数时打印一次警告，便于发现「一轮处理卡死拖住整个会话」
    SLOW_WAIT_WARNING_SECONDS = 30.0

    def __init__(self) -> None:
        # session_id -> 该会话的锁
        self._locks: Dict[str, asyncio.Lock] = {}
        # session_id -> 正在等待/持有该会话执行权的任务数
        self._waiters: Dict[str, int] = {}
        # session_id -> 当前持有者开始执行的时间戳
        self._started_at: Dict[str, float] = {}
        self._total_waits = 0
        self._total_wait_seconds = 0.0
        # session_id -> 排队等待插入当前轮次的用户消息（FIFO）
        self._pending: Dict[str, List[PendingMessage]] = {}

    # ------------------------------------------------------------------
    # 准入 / 释放
    # ------------------------------------------------------------------

    async def acquire(
        self,
        session_id: str,
        *,
        wait_warning_seconds: Optional[float] = None,
    ) -> None:
        """获取会话执行权；已被占用时按到达顺序等待。

        Args:
            session_id: 会话 ID
            wait_warning_seconds: 等待多久后打印警告，默认使用类常量
        """
        lock = self._locks.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[session_id] = lock

        self._waiters[session_id] = self._waiters.get(session_id, 0) + 1

        if not lock.locked():
            await lock.acquire()
            self._started_at[session_id] = time.monotonic()
            return

        # 已被占用：进入 FIFO 等待队列。等待提示由独立协程负责，
        # 避免用 wait_for 打断 acquire 而使等待者失去排队位置。
        self._total_waits += 1
        threshold = (
            self.SLOW_WAIT_WARNING_SECONDS
            if wait_warning_seconds is None
            else wait_warning_seconds
        )
        wait_started = time.monotonic()
        warn_task = asyncio.create_task(
            self._warn_if_slow(session_id, wait_started, threshold)
        )
        try:
            await lock.acquire()
        except asyncio.CancelledError:
            self._waiters[session_id] = max(0, self._waiters.get(session_id, 1) - 1)
            self._cleanup_if_idle(session_id)
            raise
        finally:
            warn_task.cancel()

        self._total_wait_seconds += time.monotonic() - wait_started
        self._started_at[session_id] = time.monotonic()

    async def _warn_if_slow(
        self,
        session_id: str,
        wait_started: float,
        threshold: float,
    ) -> None:
        """等待超过阈值后打印一次排队警告。"""
        try:
            await asyncio.sleep(threshold)
        except asyncio.CancelledError:
            return

        elapsed = time.monotonic() - wait_started
        logger.warning(
            f"Session {session_id} queued for {elapsed:.1f}s waiting for the "
            "previous turn to finish (holder may be stuck in a long tool call)"
        )

    def release(self, session_id: str) -> None:
        """释放会话执行权。"""
        lock = self._locks.get(session_id)
        if lock is None or not lock.locked():
            return

        self._started_at.pop(session_id, None)
        self._waiters[session_id] = max(0, self._waiters.get(session_id, 1) - 1)
        lock.release()
        self._cleanup_if_idle(session_id)

    def _cleanup_if_idle(self, session_id: str) -> None:
        """会话无持有者也无等待者时回收锁对象，避免字典无限增长。"""
        if self._waiters.get(session_id, 0) > 0:
            return
        lock = self._locks.get(session_id)
        if lock is not None and lock.locked():
            return
        self._locks.pop(session_id, None)
        self._waiters.pop(session_id, None)
        self._started_at.pop(session_id, None)

    # ------------------------------------------------------------------
    # 排队消息（插话）收件箱
    # ------------------------------------------------------------------

    def enqueue_pending(self, session_id: str, text: str) -> PendingMessage:
        """登记一条等待插入当前轮次的消息。

        只有在该会话已有处理在进行时才有意义：调用方先判断 ``is_busy`` 再登记，
        否则消息应当直接开新的一轮处理。
        """
        entry = PendingMessage(text=str(text or ""))
        self._pending.setdefault(session_id, []).append(entry)
        logger.info(
            f"Session {session_id} queued a message for in-flight turn "
            f"(pending={len(self._pending[session_id])})"
        )
        return entry

    def take_pending(self, session_id: str) -> Optional[str]:
        """取出并合并当前轮次可插入的排队消息，返回合并后的文本。

        合并多条而不是只取一条，是为了避免用户连发三句时模型只看到第一句。
        被取走的消息标记为已消费，其后获得执行权时不会重复处理。
        """
        entries = self._pending.get(session_id)
        if not entries:
            return None

        # 只取本轮之前登记的（执行中也不会有并发登记，全部取走即可）
        taken = [entry for entry in entries if not entry.consumed]
        if not taken:
            self._pending.pop(session_id, None)
            return None

        for entry in taken:
            entry.consumed = True
        self._pending.pop(session_id, None)

        text = "\n".join(entry.text.strip() for entry in taken if entry.text.strip())
        if not text:
            return None

        logger.info(
            f"Session {session_id} injected {len(taken)} queued message(s) "
            "into the in-flight turn"
        )
        return text

    def discard_pending(self, session_id: str) -> None:
        """丢弃该会话的排队消息（如用户主动取消任务时）。"""
        self._pending.pop(session_id, None)

    def has_pending(self, session_id: str) -> bool:
        """该会话是否有尚未被消费的排队消息。"""
        entries = self._pending.get(session_id) or []
        return any(not entry.consumed for entry in entries)

    def pending_count(self, session_id: str) -> int:
        """返回该会话尚未被消费的排队消息数量。"""
        entries = self._pending.get(session_id) or []
        return sum(1 for entry in entries if not entry.consumed)

    def drain_pending(self, session_id: str) -> List[str]:
        """取出全部未消费的排队消息文本（不合并），用于本轮结束后的补救。

        正常情况下排队消息会被本轮在工具批次之间取走；若本轮因为取消、异常或
        直接输出而没有走到插话点，这些消息就没人消费。调用方据此把它们当作独立
        的新消息重新处理，避免用户说的话石沉大海。
        """
        entries = self._pending.pop(session_id, None) or []
        pending = [
            entry.text.strip()
            for entry in entries
            if not entry.consumed and entry.text.strip()
        ]
        if pending:
            logger.info(
                f"Session {session_id} drains {len(pending)} unconsumed queued "
                "message(s) for follow-up processing"
            )
        return pending

    # ------------------------------------------------------------------
    # 运行态查询
    # ------------------------------------------------------------------

    def is_busy(self, session_id: str) -> bool:
        """会话是否正在处理中。"""
        lock = self._locks.get(session_id)
        return bool(lock is not None and lock.locked())

    def busy_sessions(self) -> List[str]:
        """当前正在处理的会话列表。"""
        return [sid for sid, lock in self._locks.items() if lock.locked()]

    def running_seconds(self, session_id: str) -> Optional[float]:
        """会话当前这轮已运行秒数；未在运行返回 None。"""
        started = self._started_at.get(session_id)
        if started is None:
            return None
        return time.monotonic() - started

    def stats(self) -> dict:
        """闸门统计信息，供健康检查与问题排查使用。

        字段说明：
        - busy_sessions：正在执行一轮的会话
        - tracked_sessions：锁对象数，正常情况应随释放归零
        - queued_messages：等待注入当前轮的排队消息总数
        - total_waits / total_wait_seconds：只在真实排队时累计。
          串行复用（前一轮刚好结束、没等待）不计入，所以该指标
          反映的是排队压力，不是调用次数。
        """
        return {
            "busy_sessions": len(self.busy_sessions()),
            "tracked_sessions": len(self._locks),
            "queued_messages": sum(len(items) for items in self._pending.values()),
            "total_waits": self._total_waits,
            "total_wait_seconds": round(self._total_wait_seconds, 3),
        }

    def reset(self) -> None:
        """清空全部状态（仅用于测试）。"""
        self._locks.clear()
        self._waiters.clear()
        self._started_at.clear()
        self._pending.clear()
        self._total_waits = 0
        self._total_wait_seconds = 0.0


# 进程级单例：Web 聊天、WebSocket、IM 渠道、定时任务共用同一闸门，
# 否则各链路各自的锁无法阻止跨链路并发。
_gate: Optional[SessionTurnGate] = None


def get_session_gate() -> SessionTurnGate:
    """获取进程级会话闸门。"""
    global _gate
    if _gate is None:
        _gate = SessionTurnGate()
    return _gate


def reset_session_gate() -> None:
    """重置进程级闸门（仅用于测试）。"""
    global _gate
    _gate = SessionTurnGate()
