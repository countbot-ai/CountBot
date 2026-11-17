"""会话级执行闸门测试

覆盖：串行准入、FIFO 顺序、排队消息注入与去重、异常路径释放、统计信息。
"""

import asyncio

import pytest

from backend.modules.agent.session_gate import SessionTurnGate


def run(coro):
    """在独立事件循环中执行协程，避免污染 pytest 的默认循环。"""
    return asyncio.run(coro)


def test_acquire_release_basic():
    gate = SessionTurnGate()
    assert gate.is_busy("s1") is False

    async def scenario():
        await gate.acquire("s1")
        assert gate.is_busy("s1") is True
        gate.release("s1")
        assert gate.is_busy("s1") is False

    run(scenario())


def test_same_session_serialized_in_order():
    """同一会话的任务必须串行，且按到达顺序执行。"""
    gate = SessionTurnGate()
    order = []

    async def worker(name: str):
        await gate.acquire("s1")
        try:
            order.append(f"{name}-enter")
            await asyncio.sleep(0.02)
            order.append(f"{name}-exit")
        finally:
            gate.release("s1")

    async def scenario():
        await asyncio.gather(worker("a"), worker("b"), worker("c"))

    run(scenario())

    # 串行意味着进出必须严格成对，不能出现 a-enter, b-enter 交错
    assert order == [
        "a-enter", "a-exit",
        "b-enter", "b-exit",
        "c-enter", "c-exit",
    ]


def test_different_sessions_run_concurrently():
    """不同会话之间不应互相阻塞。"""
    gate = SessionTurnGate()
    flags = []

    async def worker(session_id: str):
        await gate.acquire(session_id)
        try:
            flags.append(session_id)
            await asyncio.sleep(0.02)
        finally:
            gate.release(session_id)

    async def scenario():
        await asyncio.gather(worker("s1"), worker("s2"))

    run(scenario())
    assert set(flags) == {"s1", "s2"}
    assert gate.is_busy("s1") is False
    assert gate.is_busy("s2") is False


def test_pending_message_merged_and_consumed_once():
    """排队消息应被合并取出，且只能取一次。"""
    gate = SessionTurnGate()
    gate.enqueue_pending("s1", "第一条")
    gate.enqueue_pending("s1", "第二条")

    merged = gate.take_pending("s1")
    assert merged == "第一条\n第二条"
    # 已消费，不应再次取到，避免同一条消息被两轮处理
    assert gate.take_pending("s1") is None


def test_pending_discard():
    gate = SessionTurnGate()
    gate.enqueue_pending("s1", "丢弃我")
    gate.discard_pending("s1")
    assert gate.take_pending("s1") is None


def test_release_without_acquire_is_noop():
    """未获取执行权时释放不应抛错，也不应破坏状态。"""
    gate = SessionTurnGate()
    gate.release("unknown")
    assert gate.is_busy("unknown") is False


def test_stats_report_busy_and_queue():
    gate = SessionTurnGate()
    gate.enqueue_pending("s1", "排队中")
    stats = gate.stats()
    assert stats["queued_messages"] == 1
    assert stats["busy_sessions"] == 0


def test_lock_cleanup_after_release():
    """全部释放后不应残留锁对象，避免字典无限增长。"""
    gate = SessionTurnGate()

    async def scenario():
        await gate.acquire("s1")
        gate.release("s1")

    run(scenario())
    assert gate.stats()["tracked_sessions"] == 0


def test_acquire_cancelled_does_not_deadlock():
    """等待中被取消时应正确回退等待计数，后续仍可正常获取。"""
    gate = SessionTurnGate()

    async def scenario():
        await gate.acquire("s1")

        async def waiter():
            await gate.acquire("s1")

        task = asyncio.create_task(waiter())
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        gate.release("s1")
        # 取消的等待者不应占住会话
        assert gate.is_busy("s1") is False
        await gate.acquire("s1")
        gate.release("s1")

    run(scenario())


def test_slow_wait_warning_does_not_break_queue():
    """等待告警只是提示，不影响后续获取到执行权。"""
    gate = SessionTurnGate()

    async def scenario():
        await gate.acquire("s1")
        acquired = asyncio.Event()

        async def waiter():
            await gate.acquire("s1", wait_warning_seconds=0.01)
            acquired.set()
            gate.release("s1")

        task = asyncio.create_task(waiter())
        await asyncio.sleep(0.05)
        gate.release("s1")
        await asyncio.wait_for(acquired.wait(), timeout=1.0)
        await task

    run(scenario())
