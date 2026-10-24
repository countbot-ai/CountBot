"""AgentLoop.process_message 拆分重构的特征测试基线

锁定巨方法拆分前的关键分支行为：
- 纯文本流式直出（yield_intermediate 两种模式）
- 工具调用批次按 id 去重
- 迭代/工具额度耗尽时的 warning 文案
- key rotation 分支（is_error chunk 触发轮换）
"""

import asyncio

import pytest

from backend.modules.providers.base import ToolCall


class _ScriptedProvider:
    """按脚本产出 chunk 的假 provider，脚本为 list[list[StreamChunk 参数 dict]]。"""

    def __init__(self, scripts):
        self.scripts = scripts
        self.calls = 0

    async def chat_stream(self, messages, tools=None, **kwargs):
        from backend.modules.providers.base import StreamChunk

        idx = min(self.calls, len(self.scripts) - 1)
        self.calls += 1
        for kwargs_chunk in self.scripts[idx]:
            yield StreamChunk(**kwargs_chunk)


class _MinimalTools:
    """最小工具替身：可配置要返回的工具定义与执行结果。"""

    def __init__(self, definitions=None, succeed=True):
        self.definitions = definitions or []
        self.succeed = succeed
        self.executed = []

    def get_definitions(self):
        return self.definitions

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

    def execute_outcome(self, **kwargs):
        from backend.modules.tools.execution import (
            ExecutionState,
            RetrySafety,
            SideEffectState,
            ToolExecutionOutcome,
        )

        self.executed.append(kwargs.get("tool_name") or kwargs.get("correlation_id"))
        if self.succeed:
            return ToolExecutionOutcome(
                state=ExecutionState.SUCCEEDED,
                display_text="工具结果文本",
                retry_safety=RetrySafety.SAFE,
                side_effect_state=SideEffectState.NONE,
            )
        return ToolExecutionOutcome(
            state=ExecutionState.FAILED,
            display_text="工具失败文本",
            retryable=False,
            retry_safety=RetrySafety.UNSAFE,
            side_effect_state=SideEffectState.UNKNOWN,
        )


def _make_loop(provider, tools=None, max_iterations=6):
    from backend.modules.agent.loop import AgentLoop

    loop = AgentLoop(provider=provider, workspace=None, tools=tools,
                     max_iterations=max_iterations)
    return loop


def _collect(coro_gen):
    chunks = []

    async def scenario():
        async for chunk in coro_gen:
            chunks.append(chunk)

    asyncio.run(scenario())
    return chunks


def test_plain_text_streaming_intermediate():
    """纯文本响应：yield_intermediate=True 时逐 chunk 直出。"""
    provider = _ScriptedProvider([
        [{"content": "你好"}, {"content": "，世界"}, {"finish_reason": "stop"}],
    ])
    loop = _make_loop(provider)
    chunks = _collect(loop.process_message(message="hi", session_id="s-plain",
                                           context=[], yield_intermediate=True))
    assert "".join(chunks) == "你好，世界"


def test_plain_text_non_intermediate_single_yield():
    """yield_intermediate=False 时整段内容在最后一次性补发。"""
    provider = _ScriptedProvider([
        [{"content": "第一段"}, {"content": "第二段"}, {"finish_reason": "stop"}],
    ])
    loop = _make_loop(provider)
    chunks = _collect(loop.process_message(message="hi", session_id="s-plain2",
                                           context=[], yield_intermediate=False))
    # 非流式模式：过程中不 yield，结束时一次性补发完整内容
    assert chunks == ["第一段第二段"]


def test_duplicate_tool_call_ids_deduped():
    """同一批次内重复 tool_call id 必须去重，只执行一次。"""
    tools = _MinimalTools()
    provider = _ScriptedProvider([
        [
            {"tool_call": ToolCall(id="dup_1", name="read_file", arguments={"a": 1})},
            {"tool_call": ToolCall(id="dup_1", name="read_file", arguments={"a": 1})},
            {"finish_reason": "tool_calls"},
        ],
        [{"content": "完成"}, {"finish_reason": "stop"}],
    ])
    loop = _make_loop(provider, tools=tools)
    chunks = _collect(loop.process_message(message="跑一下", session_id="s-dup",
                                           context=[]))
    assert tools.executed.count("read_file") == 1
    assert "完成" in "".join(chunks)


def test_tool_budget_warning_emitted():
    """工具调用额度耗尽时必须输出限额提示。max_iterations=1 下迭代与工具
    额度同为 1；批次正常完成且无中止，按修正后的语义提示迭代额度耗尽
    （"工具调用次数"文案专属于批次被中止的 tool_call_limit_reached 场景）。"""
    tools = _MinimalTools()
    provider = _ScriptedProvider([
        [{"tool_call": ToolCall(id="c1", name="read_file", arguments={})},
         {"finish_reason": "tool_calls"}],
        [{"content": "答案"}, {"finish_reason": "stop"}],
    ])
    loop = _make_loop(provider, tools=tools, max_iterations=1)
    chunks = _collect(loop.process_message(message="跑", session_id="s-budget",
                                           context=[]))
    output = "".join(chunks)
    assert "[达到最大迭代次数 1]" in output
    assert len(tools.executed) == 1


def test_error_chunk_without_rotation_aborts_stream():
    """is_error chunk 且无 key rotation 可用时：yield 错误文本并终止。"""
    provider = _ScriptedProvider([
        [{"error": "上游炸了", "raw_error": "上游炸了"}],
    ])
    loop = _make_loop(provider)
    chunks = _collect(loop.process_message(message="hi", session_id="s-err",
                                           context=[]))
    assert chunks == ["上游炸了"]


def test_key_rotation_restares_turn_with_new_provider():
    """key rotation 修复后的语义：
    - rotation 成功且本轮尚未输出内容：用新 provider 重新发起本轮请求，
      不再出现空回复（修复前：当前流结束即 break，用户收到空输出）；
    - 错误文本不被 yield。
    """

    class _RotatableProvider(_ScriptedProvider):
        provider_id = "p1"

    provider = _RotatableProvider([
        [{"error": "key 失效", "raw_error": "invalid_api_key"}],
        [{"content": "轮换后成功"}, {"finish_reason": "stop"}],
    ])
    loop = _make_loop(provider)

    import backend.modules.agent.loop as loop_mod

    original = loop_mod.AgentLoop._try_key_rotation

    def fake_rotation(self, active_provider, error_text):
        self.rotation_happened = True
        return active_provider  # 模拟轮换"成功"，返回同实例（脚本按调用次数推进）

    loop_mod.AgentLoop._try_key_rotation = fake_rotation
    try:
        chunks = _collect(loop.process_message(message="hi", session_id="s-rot",
                                               context=[]))
    finally:
        loop_mod.AgentLoop._try_key_rotation = original

    assert getattr(loop, "rotation_happened", False)
    assert "key 失效" not in "".join(chunks)
    assert "轮换后成功" in "".join(chunks)


def test_key_rotation_with_prior_content_keeps_consuming():
    """rotation 时本轮已 yield 过内容：不重发（避免用户看到重复），
    保持原语义继续消费当前流剩余 chunk。"""

    class _RotatableProvider(_ScriptedProvider):
        provider_id = "p1"

    provider = _RotatableProvider([
        [{"content": "开头"}, {"error": "key 失效", "raw_error": "invalid_api_key"}],
    ])
    loop = _make_loop(provider)

    import backend.modules.agent.loop as loop_mod

    original = loop_mod.AgentLoop._try_key_rotation

    def fake_rotation(self, active_provider, error_text):
        return active_provider

    loop_mod.AgentLoop._try_key_rotation = fake_rotation
    try:
        chunks = _collect(loop.process_message(message="hi", session_id="s-rot2",
                                               context=[]))
    finally:
        loop_mod.AgentLoop._try_key_rotation = original

    # 已输出的"开头"保留；错误被吞；流结束无工具调用 → break（不重发）
    assert chunks == ["开头"]


def test_grace_turn_gives_injected_message_a_reply():
    """回归：插话额度放宽曾写在 while 退出之后——循环已结束，+1 不可能
    生效，"额外放行一轮"实际只是抑制警告，插话吸收后得不到任何回复。
    修复后：吸收插话即放行一轮，插话必须得到回应。"""
    tools = _MinimalTools()
    provider = _ScriptedProvider([
        # 第 1 轮（也是原额度下的最后一轮）：工具调用
        [{"tool_call": ToolCall(id="c1", name="read_file", arguments={})},
         {"finish_reason": "tool_calls"}],
        # 第 2 轮（修复后由插话放行）：正常回答
        [{"content": "插话已收到，这是回应"}, {"finish_reason": "stop"}],
    ])
    loop = _make_loop(provider, tools=tools, max_iterations=1)

    gate_state = {"pending": "顺便看下日志"}

    def pending_provider():
        text = gate_state["pending"]
        gate_state["pending"] = None
        return text

    chunks = _collect(loop.process_message(
        message="跑个任务", session_id="s-grace", context=[],
        pending_message_provider=pending_provider,
    ))
    output = "".join(chunks)
    # 插话放行的第二轮必须真实执行并输出回应
    assert "插话已收到，这是回应" in output, f"插话未得到回应，输出: {output!r}"
    # 插话轮无新工具调用：不应出现"工具调用次数"误报
    assert "[达到最大工具调用次数" not in output
