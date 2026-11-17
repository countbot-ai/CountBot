"""重复工具调用熔断、工具超时与无限额度语义测试。"""

import pytest

from backend.modules.providers.base import ToolCall


def _workspace():
    from pathlib import Path

    return Path(__file__).resolve().parent


class _RepeatProvider:
    """按脚本连续发出工具调用，最后一轮收尾。"""

    def __init__(self, rounds: int = 5, commands=None):
        self.rounds = rounds
        self.commands = commands
        self.calls = 0
        self.seen_messages = []

    async def chat_stream(self, messages, tools=None, **kwargs):
        from backend.modules.providers.base import StreamChunk

        self.calls += 1
        self.seen_messages = messages
        if self.calls <= self.rounds:
            command = (
                self.commands[self.calls - 1]
                if self.commands
                else "newapi-ops summary --today"
            )
            yield StreamChunk(
                usage={"prompt_tokens": 10, "completion_tokens": 5},
                tool_call=ToolCall(
                    id=f"call_{self.calls}",
                    name="exec",
                    arguments={"command": command},
                ),
            )
            yield StreamChunk(finish_reason="tool_calls")
        else:
            yield StreamChunk(content="最终回答")
            yield StreamChunk(finish_reason="stop")


class _CountingTools:
    """统计真实执行次数的最小工具替身。"""

    def __init__(self, fail_times: int = 0):
        self.executions = 0
        self.fail_times = fail_times

    def get_definitions(self):
        return []

    def set_session_id(self, *a):
        pass

    def set_channel(self, *a):
        pass

    def set_cancel_token(self, *a):
        pass

    def set_tool_event_handler(self, *a):
        pass

    def get_tool(self, *a):
        return None

    async def execute_outcome(self, **kwargs):
        from backend.modules.tools.execution import (
            ErrorCategory,
            ExecutionState,
            RetrySafety,
            SideEffectState,
            ToolExecutionOutcome,
        )

        self.executions += 1
        if self.executions <= self.fail_times:
            return ToolExecutionOutcome(
                operation_id=f"op-{self.executions}",
                attempt_id=f"att-{self.executions}",
                attempt_ordinal=1,
                tool_name="exec",
                state=ExecutionState.FAILED,
                display_text="命令超时",
                duration_ms=1,
                error_category=ErrorCategory.TIMEOUT,
                retryable=True,
                retry_safety=RetrySafety.SAFE,
                side_effect_state=SideEffectState.NOT_APPLICABLE,
            )
        return ToolExecutionOutcome(
            operation_id=f"op-{self.executions}",
            attempt_id=f"att-{self.executions}",
            attempt_ordinal=1,
            tool_name="exec",
            state=ExecutionState.SUCCEEDED,
            display_text="summary output",
            duration_ms=1,
            output="summary output",
            retry_safety=RetrySafety.SAFE,
            side_effect_state=SideEffectState.NOT_APPLICABLE,
        )


async def _run(provider, tools, session_id="s"):
    from backend.modules.agent.loop import AgentLoop

    loop = AgentLoop(provider=provider, workspace=_workspace(), tools=tools)
    chunks = []
    async for chunk in loop.process_message(
        message="查一下", session_id=session_id, context=[]
    ):
        chunks.append(chunk)
    return "".join(chunks)


@pytest.mark.asyncio
async def test_identical_tool_calls_are_executed_once_cached():
    """同一条命令连发 3 次，只真正执行 2 次，第 3 次回放上次结果。"""
    from backend.modules.agent.loop import MAX_IDENTICAL_TOOL_CALLS, AgentLoop

    provider = _RepeatProvider(rounds=3)
    tools = _CountingTools()
    loop = AgentLoop(provider=provider, workspace=_workspace(), tools=tools)

    chunks = []
    async for chunk in loop.process_message(
        message="查一下", session_id="s-repeat", context=[]
    ):
        chunks.append(chunk)

    assert tools.executions == MAX_IDENTICAL_TOOL_CALLS
    tool_messages = [m for m in provider.seen_messages if m.get("role") == "tool"]
    skipped = [m for m in tool_messages if "[重复调用拦截]" in m["content"]]
    assert len(skipped) == 3 - MAX_IDENTICAL_TOOL_CALLS
    # 回放的是上次结果，而不是让模型空手重试
    assert "summary output" in skipped[0]["content"]


@pytest.mark.asyncio
async def test_exec_output_variants_count_as_same_command():
    """换 head/tail、加 2>/dev/null、加前导 cd —— 都是同一条命令，应被拦。"""
    from backend.modules.agent.loop import MAX_IDENTICAL_TOOL_CALLS

    provider = _RepeatProvider(
        rounds=4,
        commands=[
            "newapi-ops summary --today | head -120",
            "newapi-ops summary --today | tail -12",
            "newapi-ops summary --today 2>/dev/null",
            "cd /opt && newapi-ops summary --today",
        ],
    )
    tools = _CountingTools()
    await _run(provider, tools, session_id="s-variants")

    assert tools.executions == MAX_IDENTICAL_TOOL_CALLS


@pytest.mark.asyncio
async def test_failed_call_may_be_retried():
    """失败/超时不计入连续重复，模型应当能用同一调用重试。"""
    provider = _RepeatProvider(rounds=4)
    tools = _CountingTools(fail_times=2)
    await _run(provider, tools, session_id="s-retry")

    # 前两次失败不计数，第三次、第四次成功 —— 4 次都真实执行
    assert tools.executions == 4


@pytest.mark.asyncio
async def test_repeat_skips_hard_stop_the_loop():
    """连续被熔断达到阈值后必须硬停止，不能无限空转。"""
    from backend.modules.agent.loop import MAX_CONSECUTIVE_REPEAT_SKIPS

    provider = _RepeatProvider(rounds=10)
    tools = _CountingTools()
    output = await _run(provider, tools, session_id="s-hardstop")

    assert tools.executions == 2
    # 第 3 次拦截时硬停止，不会再发下一次模型请求
    assert provider.calls == 2 + MAX_CONSECUTIVE_REPEAT_SKIPS
    assert "已停止本轮工具调用" in output


@pytest.mark.asyncio
async def test_repeat_skips_hard_stop_keeps_tool_result_pairing():
    """一批里多个相同调用触发硬停止时，未执行的调用也要有占位结果。"""
    from backend.modules.agent.loop import MAX_CONSECUTIVE_REPEAT_SKIPS

    class _BatchProvider:
        def __init__(self, batch: int = 6):
            self.batch = batch
            self.calls = 0
            self.seen_messages = []

        async def chat_stream(self, messages, tools=None, **kwargs):
            from backend.modules.providers.base import StreamChunk

            self.calls += 1
            self.seen_messages = messages
            if self.calls == 1:
                for index in range(self.batch):
                    yield StreamChunk(
                        tool_call=ToolCall(
                            id=f"b{index}",
                            name="exec",
                            arguments={"command": "newapi-ops summary --today"},
                        )
                    )
                yield StreamChunk(finish_reason="tool_calls")
            else:
                yield StreamChunk(content="done")
                yield StreamChunk(finish_reason="stop")

    provider = _BatchProvider(batch=6)
    tools = _CountingTools()
    output = await _run(provider, tools, session_id="s-batch")

    assert tools.executions == 2
    assert "已停止本轮工具调用" in output

    # assistant(tool_calls) 与 tool 结果必须一一配对
    assistant_ids = []
    tool_ids = []
    for message in provider.seen_messages:
        if message.get("role") == "assistant":
            assistant_ids.extend(
                call["id"] for call in (message.get("tool_calls") or [])
            )
        elif message.get("role") == "tool":
            tool_ids.append(message.get("tool_call_id"))
    assert len(assistant_ids) == 6
    assert sorted(tool_ids) == sorted(assistant_ids)
    assert MAX_CONSECUTIVE_REPEAT_SKIPS >= 1


@pytest.mark.asyncio
async def test_alternating_calls_are_not_blocked():
    """A/B 交替（例如改完代码再跑同一条测试）不算连续重复。"""
    from backend.modules.agent.loop import AgentLoop

    class _AlternatingProvider:
        def __init__(self):
            self.calls = 0

        async def chat_stream(self, messages, tools=None, **kwargs):
            from backend.modules.providers.base import StreamChunk

            self.calls += 1
            if self.calls <= 4:
                cmd = "echo 1" if self.calls % 2 else "echo 2"
                yield StreamChunk(
                    tool_call=ToolCall(
                        id=f"a{self.calls}", name="exec", arguments={"command": cmd}
                    )
                )
                yield StreamChunk(finish_reason="tool_calls")
            else:
                yield StreamChunk(content="done")
                yield StreamChunk(finish_reason="stop")

    tools = _CountingTools()
    loop = AgentLoop(provider=_AlternatingProvider(), workspace=_workspace(), tools=tools)
    async for _ in loop.process_message(message="x", session_id="s-alt", context=[]):
        pass

    assert tools.executions == 4


def test_call_timeout_honours_requested_timeout():
    """命令行声明 timeout=180 时，外层超时必须大于它（数字与字符串都要认）。"""
    from backend.modules.agent.loop import AgentLoop

    loop = AgentLoop(provider=None, workspace=_workspace(), tools=None)
    configured = loop._resolve_tool_timeout_seconds()

    assert loop._resolve_call_timeout({}) == configured
    assert loop._resolve_call_timeout({"command": "x"}) == configured
    assert loop._resolve_call_timeout({"timeout": 180}) >= 185
    assert loop._resolve_call_timeout({"timeout": "180"}) >= 185
    # 非法值不能把超时改小，也不能抛异常
    assert loop._resolve_call_timeout({"timeout": "abc"}) == configured
    # 小于配置值的入参不能把超时改小
    assert loop._resolve_call_timeout({"timeout": 5}) == configured


def test_zero_means_unlimited():
    """max_iterations=0 折算为内部上界，且不产出「达到最大工具调用次数」。"""
    from backend.modules.agent.loop import (
        UNLIMITED_TOOL_BUDGET,
        AgentLoop,
        _LoopState,
        resolve_tool_budget,
    )

    assert resolve_tool_budget(0) == UNLIMITED_TOOL_BUDGET
    assert resolve_tool_budget(None) == UNLIMITED_TOOL_BUDGET
    assert resolve_tool_budget(30) == 30

    loop = AgentLoop(provider=None, workspace=_workspace(), tools=None)
    state = _LoopState(
        messages=[],
        iteration=UNLIMITED_TOOL_BUDGET,
        iteration_budget=UNLIMITED_TOOL_BUDGET,
        tool_budget_unlimited=True,
        tool_call_limit_reached=True,
    )
    assert loop._finalize_limits(state, UNLIMITED_TOOL_BUDGET) is None

    # 显式上限仍然要给出提示
    limited = _LoopState(
        messages=[],
        iteration=1,
        iteration_budget=10,
        tool_call_limit_reached=True,
    )
    warning = loop._finalize_limits(limited, 10)
    assert warning is not None and "达到最大工具调用次数 10" in warning


def test_rules_block_declares_budget_only_when_limited():
    """限次时才声明额度；批处理/落盘/去重规则始终在。"""
    from pathlib import Path

    from backend.modules.agent.context import ContextBuilder

    builder = ContextBuilder(workspace=Path(_workspace()))

    unlimited = builder._get_rules_block()
    assert "tool calls in total" not in unlimited

    limited = builder._get_rules_block(tool_budget=25)
    assert "at most 25 tool calls in total" in limited

    for expected in (
        "Batch independent steps into ONE",
        "Run an expensive command at most once",
        "file_search",
    ):
        assert expected in limited
