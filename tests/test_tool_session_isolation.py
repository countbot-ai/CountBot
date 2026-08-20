"""并发会话隔离回归测试。

背景（bug）：渠道 handler 用 ``asyncio.create_task`` 并发处理多条入站消息，
且**同一个 handler 复用同一个 ToolRegistry 与同一批工具实例**。若工具把
session_id / cancel_token / message_context 存进**实例属性**，两条并发消息会
互相覆盖：A 会话生成的文件被发到 B、取消 A 却打断 B、shell 子进程环境变量串号。

修复：这些上下文改用 per-instance ``contextvars.ContextVar`` 存储。由于
``create_task`` 会复制当前 Context，每个任务内的 ``.set()`` 只作用于自己的
Context 副本，实例虽共享但读到的值按执行上下文隔离。

本测试直接复现「两个并发任务在同一个共享工具实例上先各自 set、再各自读回」的
时序。若回退成实例属性写法，`_Rendezvous` 保证两次 set 都先于读取发生，后写者
必然覆盖前者 → 至少一个任务读到对方的值 → 测试失败。
"""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.modules.tools.spawn import SpawnTool
from backend.modules.tools.workflow_tool import WorkflowTool
from backend.modules.tools.send_media import SendMediaTool
from backend.modules.tools.shell import ExecTool
from backend.modules.tools.registry import ToolRegistry


class _Rendezvous:
    """N 路会合点：所有参与者都到达后才一起放行。

    用它强制「两个任务都完成 set 之后，才开始 read」的最坏交错，
    从而稳定复现共享实例属性被覆盖的竞态（否则时序偶发、测不出来）。
    """

    def __init__(self, parties: int) -> None:
        self._parties = parties
        self._count = 0
        self._event = asyncio.Event()

    async def wait(self) -> None:
        # 单线程事件循环内，自增与判断之间无 await，天然原子
        self._count += 1
        if self._count >= self._parties:
            self._event.set()
        await self._event.wait()


async def _run_two_session_isolation(tool, setter_name, getter):
    """在同一个 tool 实例上并发跑两个「设置不同会话 → 会合 → 读回」的任务。

    返回 {session_id: 读回的值}，隔离正确时二者应各自读回自身。
    """
    gate = _Rendezvous(2)

    async def worker(session_id: str, payload):
        # 每个 worker 作为独立 Task 运行（见下方 create_task），拥有独立 Context 副本
        getattr(tool, setter_name)(payload)
        await gate.wait()  # 等两个任务都 set 完，制造最坏交错
        return getter(tool)

    task_a = asyncio.create_task(worker("A", _payload_for("A")))
    task_b = asyncio.create_task(worker("B", _payload_for("B")))
    read_a, read_b = await asyncio.gather(task_a, task_b)
    return read_a, read_b


def _payload_for(tag: str):
    return f"session-{tag}"


# --------------------------------------------------------------------------
# 各工具的 session_id 隔离
# --------------------------------------------------------------------------

def test_spawn_tool_session_id_isolated_across_tasks():
    async def scenario():
        tool = SpawnTool(manager=object())
        return await _run_two_session_isolation(
            tool, "set_session_id", lambda t: t._session_id
        )

    read_a, read_b = asyncio.run(scenario())
    assert read_a == "session-A", f"A 任务读到了 {read_a!r}，会话上下文被串号"
    assert read_b == "session-B", f"B 任务读到了 {read_b!r}，会话上下文被串号"


def test_spawn_tool_set_context_also_isolated():
    """spawn 还有一个 set_context 入口（loop.py 单独调用），同样必须隔离。"""

    async def scenario():
        tool = SpawnTool(manager=object())
        return await _run_two_session_isolation(
            tool, "set_context", lambda t: t._session_id
        )

    read_a, read_b = asyncio.run(scenario())
    assert read_a == "session-A"
    assert read_b == "session-B"


def test_workflow_tool_session_id_isolated_across_tasks():
    async def scenario():
        tool = WorkflowTool(subagent_manager=object())
        return await _run_two_session_isolation(
            tool, "set_session_id", lambda t: t._session_id
        )

    read_a, read_b = asyncio.run(scenario())
    assert read_a == "session-A"
    assert read_b == "session-B"


def test_send_media_tool_session_id_isolated_across_tasks():
    async def scenario():
        tool = SendMediaTool()
        return await _run_two_session_isolation(
            tool, "set_session_id", lambda t: t._current_session_id
        )

    read_a, read_b = asyncio.run(scenario())
    assert read_a == "session-A"
    assert read_b == "session-B"


# --------------------------------------------------------------------------
# 取消令牌隔离（取消 A 不能打断 B）
# --------------------------------------------------------------------------

def test_spawn_tool_cancel_token_isolated_across_tasks():
    async def scenario():
        tool = SpawnTool(manager=object())
        return await _run_two_session_isolation(
            tool, "set_cancel_token", lambda t: t._cancel_token
        )

    token_a, token_b = asyncio.run(scenario())
    assert token_a == "session-A", "A 读到的取消令牌被 B 覆盖 → 取消会打断错误的会话"
    assert token_b == "session-B"


def test_workflow_tool_cancel_token_isolated_across_tasks():
    async def scenario():
        tool = WorkflowTool(subagent_manager=object())
        return await _run_two_session_isolation(
            tool, "set_cancel_token", lambda t: t._cancel_token
        )

    token_a, token_b = asyncio.run(scenario())
    assert token_a == "session-A"
    assert token_b == "session-B"


# --------------------------------------------------------------------------
# ExecTool 的 message_context 隔离（决定子进程渠道/发件人环境变量）
# --------------------------------------------------------------------------

def test_exec_tool_message_context_isolated_across_tasks(tmp_path):
    async def scenario():
        tool = ExecTool(workspace=tmp_path)

        async def worker(tag, ctx):
            tool.set_message_context(ctx)
            await gate.wait()
            return tool._message_context

        gate = _Rendezvous(2)
        ctx_a = {"metadata": {"channel": "A"}}
        ctx_b = {"metadata": {"channel": "B"}}
        ta = asyncio.create_task(worker("A", ctx_a))
        tb = asyncio.create_task(worker("B", ctx_b))
        return await asyncio.gather(ta, tb)

    read_a, read_b = asyncio.run(scenario())
    assert read_a == {"metadata": {"channel": "A"}}, "A 的消息上下文被 B 覆盖"
    assert read_b == {"metadata": {"channel": "B"}}


# --------------------------------------------------------------------------
# 端到端：走真实的 ToolRegistry.set_session_id / set_cancel_token 分发路径
# --------------------------------------------------------------------------

def test_registry_dispatch_isolates_session_across_concurrent_tasks():
    """复现生产链路：并发任务各自 registry.set_session_id(X) 后读回对应工具。

    这条路径正是 loop.process_message 每轮所走的（registry 遍历工具注入上下文）。
    """

    async def scenario():
        registry = ToolRegistry()
        spawn = SpawnTool(manager=object())
        workflow = WorkflowTool(subagent_manager=object())
        registry.register(spawn)
        registry.register(workflow)

        gate = _Rendezvous(2)

        async def worker(session_id):
            registry.set_session_id(session_id)
            registry.set_cancel_token(f"token-{session_id}")
            await gate.wait()
            # 注册表自身的 contextvar，以及被注入的两个工具，都应读到本任务的值
            return (
                registry._session_id,
                spawn._session_id,
                workflow._session_id,
                spawn._cancel_token,
                workflow._cancel_token,
            )

        ta = asyncio.create_task(worker("A"))
        tb = asyncio.create_task(worker("B"))
        return await asyncio.gather(ta, tb)

    (reg_a, spawn_a, wf_a, ctok_a, wtok_a), (reg_b, spawn_b, wf_b, ctok_b, wtok_b) = (
        asyncio.run(scenario())
    )

    assert reg_a == "A" and reg_b == "B"
    assert spawn_a == "A" and spawn_b == "B"
    assert wf_a == "A" and wf_b == "B"
    assert ctok_a == "token-A" and ctok_b == "token-B"
    assert wtok_a == "token-A" and wtok_b == "token-B"


# --------------------------------------------------------------------------
# 元测试：证明本测试确实能抓住「实例属性」写法的 bug（防止测试假阳性）
# --------------------------------------------------------------------------

def test_rendezvous_would_catch_instance_attribute_regression():
    """用一个故意用实例属性的假工具，验证 _Rendezvous 时序能暴露串号。

    若有人把某个工具改回实例属性存储，等价于这个 _BadTool，本断言表明
    在相同并发时序下它会失败——即上面的隔离测试不是摆设。
    """

    class _BadTool:
        def __init__(self):
            self._sid = None  # 共享实例属性（错误写法）

        def set_session_id(self, sid):
            self._sid = sid

    async def scenario():
        tool = _BadTool()
        return await _run_two_session_isolation(
            tool, "set_session_id", lambda t: t._sid
        )

    read_a, read_b = asyncio.run(scenario())
    # 实例属性写法下，两个任务读到的是同一个（后写者）值，无法各自隔离
    assert read_a == read_b, (
        "预期实例属性写法会串号（两任务读到同值），若此处不相等说明测试时序失效"
    )
