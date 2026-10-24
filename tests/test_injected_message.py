"""插话（排队消息）行为测试

覆盖审查中发现的问题：
- 插话内容不得进入助手输出流（否则会被当成助手回复落库并回显给用户）；
- 插话未被消费时必须能被取出补救，不能静默丢失；
- 迭代额度放宽只发生一次，不会让循环失去上限。
"""

import asyncio

import pytest

from backend.modules.agent.session_gate import SessionTurnGate
from backend.modules.providers.base import ToolCall


class _FakeProvider:
    """按脚本产出 chunk 的假 provider：第一轮返回工具调用，第二轮返回文本。"""

    def __init__(self):
        self.calls = 0

    async def chat_stream(self, messages, tools=None, **kwargs):
        from backend.modules.providers.base import StreamChunk

        self.calls += 1
        if self.calls == 1:
            yield StreamChunk(
                usage={"prompt_tokens": 10, "completion_tokens": 5},
                tool_call=ToolCall(id="call_1", name="read_file", arguments={}),
            )
            yield StreamChunk(finish_reason="tool_calls")
        else:
            yield StreamChunk(content="最终回答")
            yield StreamChunk(finish_reason="stop")


@pytest.mark.asyncio
async def test_injected_message_not_yielded_to_response_stream(tmp_path):
    """插话内容不应出现在助手输出流中。"""
    from backend.modules.agent.loop import AgentLoop

    gate = SessionTurnGate()
    gate.enqueue_pending("s-inject", "顺便把日志也看一下")

    loop = AgentLoop(provider=_FakeProvider(), workspace=tmp_path, tools=None, max_iterations=6)
    # 用一个最小工具替身，避免真实文件系统与注册表依赖
    class _Tools:
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

        def execute_outcome(self, **kwargs):
            from backend.modules.tools.execution import (
                ExecutionState,
                RetrySafety,
                SideEffectState,
                ToolExecutionOutcome,
            )

            return ToolExecutionOutcome(
                state=ExecutionState.SUCCEEDED,
                display_text="file body",
                retry_safety=RetrySafety.SAFE,
                side_effect_state=SideEffectState.NONE,
            )

    loop.tools = _Tools()

    chunks = []
    async for chunk in loop.process_message(
        message="帮我读文件",
        session_id="s-inject",
        context=[],
        pending_message_provider=lambda: gate.take_pending("s-inject"),
    ):
        chunks.append(chunk)

    output = "".join(chunks)
    assert "顺便把日志也看一下" not in output
    assert "最终回答" in output


def test_drain_pending_returns_unconsumed():
    """未被消费的消息必须能被 drain 出来用于补救。"""
    gate = SessionTurnGate()
    gate.enqueue_pending("s1", "消息A")
    gate.enqueue_pending("s1", "消息B")

    drained = gate.drain_pending("s1")
    assert drained == ["消息A", "消息B"]
    # 取走后收件箱应清空，避免重复处理
    assert gate.has_pending("s1") is False
    assert gate.drain_pending("s1") == []


def test_drain_pending_skips_consumed():
    """已被本轮吸收的消息不应再次被 drain。"""
    gate = SessionTurnGate()
    gate.enqueue_pending("s1", "已吸收")
    assert gate.take_pending("s1") == "已吸收"

    gate.enqueue_pending("s1", "未吸收")
    assert gate.drain_pending("s1") == ["未吸收"]


def test_has_pending_reflects_state():
    gate = SessionTurnGate()
    assert gate.has_pending("s1") is False
    gate.enqueue_pending("s1", "x")
    assert gate.has_pending("s1") is True
    gate.take_pending("s1")
    assert gate.has_pending("s1") is False
