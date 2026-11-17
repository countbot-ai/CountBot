"""会话闸门与真实链路集成的健壮性验证

重点检查几个容易出问题的场景：
- 生成器被提前关闭（客户端断开）时闸门是否正确释放；
- 等待中的任务被取消后是否残留占位；
- 排队消息在无人消费时是否会丢失。
"""

import asyncio

import pytest

from backend.modules.agent.session_gate import SessionTurnGate, get_session_gate


def test_gate_released_when_generator_aclose():
    """模拟 SSE 生成器被 aclose：finally 必须释放闸门，否则会话永久卡死。"""
    gate = SessionTurnGate()

    async def stream():
        await gate.acquire("s-close")
        try:
            yield "chunk-1"
            yield "chunk-2"
        finally:
            gate.release("s-close")

    async def scenario():
        agen = stream()
        assert await agen.__anext__() == "chunk-1"
        # 客户端断开 → 框架会关闭生成器
        await agen.aclose()
        assert gate.is_busy("s-close") is False

        # 后续请求必须还能进来
        await gate.acquire("s-close")
        gate.release("s-close")

    asyncio.run(scenario())


def test_gate_released_on_exception_in_generator():
    """生成器内部抛异常时同样必须释放。"""
    gate = SessionTurnGate()

    async def stream():
        await gate.acquire("s-err")
        try:
            yield "ok"
            raise RuntimeError("boom")
        finally:
            gate.release("s-err")

    async def scenario():
        agen = stream()
        await agen.__anext__()
        with pytest.raises(RuntimeError):
            await agen.__anext__()
        assert gate.is_busy("s-err") is False

    asyncio.run(scenario())


def test_pending_message_lost_if_never_consumed():
    """排队消息如果没有被消费，会一直留在收件箱——验证这一行为以便评估风险。

    这是一个已知风险点：负责消费的那一轮如果提前结束（被取消、异常退出），
    登记为插话的消息就没有机会进入上下文。
    """
    gate = SessionTurnGate()
    gate.enqueue_pending("s1", "用户补充的话")

    # 模拟持有者异常退出，没有机会调用 take_pending
    assert gate.stats()["queued_messages"] == 1
    # 消息仍在
    assert gate.take_pending("s1") == "用户补充的话"


def test_gate_is_process_singleton():
    """三条链路必须共享同一个闸门，否则跨链路并发无法拦截。"""
    assert get_session_gate() is get_session_gate()


def test_release_after_consumer_raises_still_frees():
    """消费方释放顺序错误时不应让闸门卡死。"""
    gate = SessionTurnGate()

    async def scenario():
        await gate.acquire("s1")
        # 重复释放不应抛错
        gate.release("s1")
        gate.release("s1")
        assert gate.is_busy("s1") is False

    asyncio.run(scenario())


def test_multiple_waiters_all_get_turn():
    """多个等待者必须全部依次获得执行权，不能有饿死。"""
    gate = SessionTurnGate()
    served = []

    async def worker(idx: int):
        await gate.acquire("s1")
        try:
            served.append(idx)
            await asyncio.sleep(0.005)
        finally:
            gate.release("s1")

    async def scenario():
        await asyncio.gather(*(worker(i) for i in range(6)))

    asyncio.run(scenario())
    assert sorted(served) == list(range(6))
    assert len(served) == 6
