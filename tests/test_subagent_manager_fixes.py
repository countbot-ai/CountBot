"""SubagentManager 修复回归测试

覆盖：
- cancel_tasks 按归属过滤：取消 A 工作流的任务不得波及 B 的任务
- delete_task 运行中任务先取消后删除（取消必须真实生效）
- 结果预算：超限截断并标注
- 并发信号量：超过上限的任务排队执行
- 无活动看门狗：不活动的任务被按 TIMEOUT 分类中止
"""

import asyncio
import time
from types import SimpleNamespace

import pytest

from backend.modules.agent.subagent import SubagentManager, SubagentTask, TaskStatus
from backend.modules.agent.task_manager import CancellationToken
from backend.modules.providers.base import StreamChunk
from backend.modules.tools.execution import (
    ErrorCategory, ExecutionState, SideEffectState, ToolResult,
)



class _SlowProvider:
    """长任务 provider：流内长时间无产出，用于看门狗测试。"""

    def __init__(self, hang_seconds: float = 5.0):
        self.hang_seconds = hang_seconds

    async def chat_stream(self, messages, tools=None, **kwargs):
        yield StreamChunk(content="开始")
        await asyncio.sleep(self.hang_seconds)
        yield StreamChunk(content="结束")


@pytest.mark.asyncio
async def test_cancel_tasks_filtering_by_ownership(tmp_path):
    """取消 A 的任务集合不得波及 B 的任务（跨工作流污染回归）。"""
    config = SimpleNamespace(
        security=SimpleNamespace(command_timeout=5, subagent_timeout=60),
        model=SimpleNamespace(max_iterations=3, model="t", temperature=0,
                              max_tokens=100, thinking_enabled=False),
        injection=None,
    )
    class _HangForeverProvider:
        async def chat_stream(self, messages, tools=None, **kwargs):
            await asyncio.sleep(30)
            yield StreamChunk(content="never")

    manager = SubagentManager(
        _HangForeverProvider(), tmp_path, "t",
        config_loader=SimpleNamespace(config=config),
    )

    task_a = manager.create_task("A", "a")
    task_b = manager.create_task("B", "b")
    await manager.execute_task(task_a)
    await manager.execute_task(task_b)
    await asyncio.sleep(0.05)
    assert task_a in manager.running_tasks and task_b in manager.running_tasks

    # 只取消 A 的集合
    cancelled = await manager.cancel_tasks({task_a})
    assert cancelled == 1
    await asyncio.sleep(0.05)

    # A 已停止，B 仍在运行
    assert manager.tasks[task_a].status in (TaskStatus.CANCELLED, TaskStatus.FAILED)
    assert manager.tasks[task_b].status is TaskStatus.RUNNING
    assert task_b in manager.running_tasks


class _HangForeverProvider:
    async def chat_stream(self, messages, tools=None, **kwargs):
        await asyncio.sleep(30)
        yield StreamChunk(content="never")


@pytest.mark.asyncio
async def test_delete_running_task_cancels_runner(tmp_path):
    """回归：删除运行中任务必须真实取消 runner（原实现先删登记再异步
    取消，取消逻辑找不到任务，幽灵任务继续运行）。"""
    config = SimpleNamespace(
        security=SimpleNamespace(command_timeout=5, subagent_timeout=60),
        model=SimpleNamespace(max_iterations=3, model="t", temperature=0,
                              max_tokens=100, thinking_enabled=False),
        injection=None,
    )
    manager = SubagentManager(
        _HangForeverProvider(), tmp_path, "t",
        config_loader=SimpleNamespace(config=config),
    )
    task_id = manager.create_task("t", "work")
    await manager.execute_task(task_id)
    await asyncio.sleep(0.05)
    assert task_id in manager.running_tasks

    assert manager.delete_task(task_id) is True

    # runner 已被取消（等待其收尾）
    runner = None
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        # 幽灵检查：原实现下 asyncio.Task 仍会继续写库
        if manager.tasks.get(task_id) is None and task_id not in manager.running_tasks:
            break
        await asyncio.sleep(0.05)
    assert task_id not in manager.running_tasks, "运行中的幽灵任务未被取消"


@pytest.mark.asyncio
async def test_result_truncated_at_budget(tmp_path):
    """结果超过预算时截断并标注完整长度。"""
    config = SimpleNamespace(
        security=SimpleNamespace(command_timeout=5, subagent_timeout=30),
        model=SimpleNamespace(max_iterations=3, model="t", temperature=0,
                              max_tokens=100, thinking_enabled=False),
        injection=None,
    )
    manager = SubagentManager(
        _ScriptedBigOutput(), tmp_path, "t",
        config_loader=SimpleNamespace(config=config),
    )
    task_id = manager.create_task("t", "produce")
    await manager.execute_task(task_id)
    task = manager.tasks[task_id]
    await asyncio.wait_for(task.done_event.wait(), 5)

    assert len(task.result) <= manager._result_budget + 120
    assert "已截断" in task.result
    assert task.status is TaskStatus.COMPLETED


class _ScriptedBigOutput:
    async def chat_stream(self, messages, tools=None, **kwargs):
        yield StreamChunk(content="x" * 150_000)
        yield StreamChunk(finish_reason="stop")


class _CountingProvider:
    """记录 provider 侧真实并发峰值，用于验证信号量是否真的拦住了执行。"""

    def __init__(self, hold_seconds: float = 0.15):
        self.hold_seconds = hold_seconds
        self.now = 0
        self.peak = 0
        self.calls = 0

    async def chat_stream(self, messages, tools=None, **kwargs):
        self.calls += 1
        self.now += 1
        self.peak = max(self.peak, self.now)
        try:
            await asyncio.sleep(self.hold_seconds)
            yield StreamChunk(content="ok")
            yield StreamChunk(finish_reason="stop")
        finally:
            self.now -= 1


@pytest.mark.asyncio
async def test_concurrency_semaphore_queues_tasks(tmp_path):
    """超过并发上限的任务排队执行：provider 侧并发不得超过上限。"""
    config = SimpleNamespace(
        security=SimpleNamespace(command_timeout=5, subagent_timeout=30),
        model=SimpleNamespace(max_iterations=3, model="t", temperature=0,
                              max_tokens=100, thinking_enabled=False),
        injection=None,
    )
    provider = _CountingProvider()
    manager = SubagentManager(
        provider, tmp_path, "t",
        config_loader=SimpleNamespace(config=config), max_concurrent=2,
    )
    ids = [manager.create_task(f"t{i}", "work") for i in range(6)]
    for tid in ids:
        await manager.execute_task(tid)

    for tid in ids:
        await asyncio.wait_for(manager.tasks[tid].done_event.wait(), timeout=15)

    # 限流的判据在执行侧：provider 同时被调用的次数不得超过上限
    assert provider.peak <= 2, f"provider 并发峰值 {provider.peak} 超过上限 2"
    assert provider.peak == 2  # 确实跑满了额度，而不是退化成串行
    assert all(manager.tasks[tid].status is TaskStatus.COMPLETED for tid in ids)


@pytest.mark.asyncio
async def test_cancel_while_queued_settles_as_cancelled(tmp_path):
    """排队中的任务被取消时必须收敛为终态，不能一直挂在 running。"""
    config = SimpleNamespace(
        security=SimpleNamespace(command_timeout=5, subagent_timeout=30),
        model=SimpleNamespace(max_iterations=3, model="t", temperature=0,
                              max_tokens=100, thinking_enabled=False),
        injection=None,
    )
    manager = SubagentManager(
        _IdleProvider(), tmp_path, "t",
        config_loader=SimpleNamespace(config=config), max_concurrent=1,
    )

    first = manager.create_task("先占额度", "work")
    await manager.execute_task(first)
    await asyncio.sleep(0)  # 让 runner 真正占用信号量

    queued = manager.create_task("排队中", "work")
    await manager.execute_task(queued)
    await manager.cancel_task(queued)

    await asyncio.wait_for(manager.tasks[queued].done_event.wait(), timeout=10)
    task = manager.tasks[queued]
    assert task.status is TaskStatus.CANCELLED
    assert task.error == "任务已被取消"
    assert manager.get_running_count() <= 1


class _IdleProvider:
    async def chat_stream(self, messages, tools=None, **kwargs):
        await asyncio.sleep(0.5)
        yield StreamChunk(content="done")
        yield StreamChunk(finish_reason="stop")


@pytest.mark.asyncio
async def test_inactivity_watchdog_aborts_stalled_task(tmp_path):
    """无活动看门狗：卡死的任务被按 TIMEOUT 分类中止，productive 任务不受影响。"""
    config = SimpleNamespace(
        security=SimpleNamespace(command_timeout=5, subagent_timeout=60),
        model=SimpleNamespace(max_iterations=3, model="t", temperature=0,
                              max_tokens=100, thinking_enabled=False),
        injection=None,
    )
    manager = SubagentManager(
        _SlowProvider(hang_seconds=10), tmp_path, "t",
        config_loader=SimpleNamespace(config=config), inactivity_seconds=0.3,
    )
    task_id = manager.create_task("t", "stall")
    await manager.execute_task(task_id)
    task = manager.tasks[task_id]
    await asyncio.wait_for(task.done_event.wait(), 5)

    assert task.aborted_by_watchdog is True
    assert task.outcome.error_category is ErrorCategory.TIMEOUT
    assert task.status is TaskStatus.FAILED
