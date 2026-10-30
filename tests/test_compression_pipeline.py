"""上下文压缩流水线测试。

``backend/modules/agent/history_compactor.py`` 拆进 ``backend/modules/compression``
后，旧的 ``tests/test_history_compactor.py`` 仍在 import 已删除模块，导致整个
测试套件在收集阶段中断。这里覆盖迁移后最要紧的两层：

- 切点安全性：任何情况下都不能把工具调用与结果切开，否则请求里会出现孤儿
  ``tool_calls`` / ``tool`` 消息；
- 压缩主流程：阈值判定、摘要替换、失败回退（不调用模型也要能收敛）。
"""

import pytest

from backend.modules.compression import (
    COMPRESSION_NOTE,
    CompactionSettings,
    CompressionEngine,
    estimate_messages_tokens,
    estimate_tokens,
)
from backend.modules.compression.boundaries import (
    align_backward,
    align_forward,
    classify_tool_pairs,
    is_safe_cut_point,
    sanitize_tool_pairs,
    turn_pair_end,
)
from backend.modules.providers.base import StreamChunk

CHARS_PER_MESSAGE = 600


def _tool_turn(call_id: str = "call_1"):
    """构造一组「assistant 发起工具调用 + tool 结果」消息。"""
    return [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": "probe", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": call_id, "content": "result"},
    ]


def _conversation(turns: int = 20):
    messages = [{"role": "system", "content": "system prompt"}]
    for index in range(turns):
        messages.append(
            {"role": "user", "content": f"question {index} " + "q" * CHARS_PER_MESSAGE}
        )
        messages.append(
            {"role": "assistant", "content": f"answer {index} " + "a" * CHARS_PER_MESSAGE}
        )
    return messages


class _FakeProvider:
    """最小 chat_stream 实现：按 8 字符切片吐摘要正文。"""

    def __init__(self, text: str = "CONDENSED_SUMMARY", error=None):
        self.text = text
        self.error = error
        self.calls = 0

    async def chat_stream(self, messages=None, tools=None, model=None, **kwargs):
        self.calls += 1
        if self.error is not None:
            raise self.error
        for index in range(0, len(self.text), 8):
            yield StreamChunk(content=self.text[index:index + 8])
        yield StreamChunk(finish_reason="stop")


# ---------------------------------------------------------------------------
# 切点安全性：旧测试的核心价值
# ---------------------------------------------------------------------------


def test_cut_point_must_not_split_tool_pairs():
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "ask"},
        *_tool_turn(),
        {"role": "assistant", "content": "done"},
    ]

    # 切在 tool 结果上会把调用与结果拆开
    assert is_safe_cut_point(messages, 3) is False
    # 切在工具组之后是安全的
    assert is_safe_cut_point(messages, 4) is True
    # 两端边界始终安全
    assert is_safe_cut_point(messages, 0) is True
    assert is_safe_cut_point(messages, len(messages)) is True


def test_align_forward_skips_leading_tool_results():
    messages = [
        {"role": "user", "content": "ask"},
        {"role": "tool", "tool_call_id": "call_1", "content": "r1"},
        {"role": "tool", "tool_call_id": "call_2", "content": "r2"},
        {"role": "assistant", "content": "done"},
    ]

    assert align_forward(messages, 1) == 3
    assert align_forward(messages, 0) == 0
    # 越过尾部时返回长度本身，而不是越界索引
    assert align_forward(messages, 4) == 4


def test_align_backward_pulls_cut_before_the_tool_group():
    messages = [
        {"role": "user", "content": "ask"},
        *_tool_turn(),
        {"role": "user", "content": "next"},
    ]

    # 切点在 next 之前会留下孤儿 tool 结果，必须回退到发起调用的 assistant
    assert align_backward(messages, 3) == 1
    assert align_backward(messages, 0) == 0


def test_turn_pair_end_keeps_tool_group_with_its_user_turn():
    messages = [
        {"role": "user", "content": "ask"},
        *_tool_turn(),
        {"role": "assistant", "content": "done"},
        {"role": "user", "content": "next"},
    ]

    assert turn_pair_end(messages, 0) == 4
    assert turn_pair_end(messages, 4) == len(messages)


def test_sanitize_drops_orphaned_results():
    messages = [
        {"role": "user", "content": "ask"},
        {"role": "tool", "tool_call_id": "missing_call", "content": "orphan"},
        {"role": "assistant", "content": "done"},
    ]

    sanitized = sanitize_tool_pairs(messages)

    assert [message["role"] for message in sanitized] == ["user", "assistant"]


def test_sanitize_strips_orphaned_calls_but_keeps_content():
    messages = [
        {"role": "user", "content": "ask"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "probe", "arguments": "{}"}}
            ],
        },
        {"role": "user", "content": "next"},
    ]

    sanitized = sanitize_tool_pairs(messages)

    # 调用没了结果，必须剥离，否则上游会拒绝；空内容补一句占位
    assert "tool_calls" not in sanitized[1]
    assert sanitized[1]["content"] == "(tool call removed)"


def test_sanitize_keeps_the_in_flight_tool_call():
    messages = [
        {"role": "user", "content": "ask"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "probe", "arguments": "{}"}}
            ],
        },
    ]

    sanitized = sanitize_tool_pairs(messages)

    # 压缩可能发生在执行器追加结果之前，最新一轮调用不能被当成孤儿
    assert sanitized[1]["tool_calls"]


def test_classify_tool_pairs_reports_both_sides():
    messages = [
        *_tool_turn("call_1"),
        {"role": "tool", "tool_call_id": "call_orphan", "content": "orphan"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": "call_2", "type": "function", "function": {"name": "probe", "arguments": "{}"}}
            ],
        },
    ]

    report = classify_tool_pairs(messages)

    assert report["declared_ids"] == {"call_1", "call_2"}
    assert report["result_call_ids"] == {"call_1"}
    assert len(report["orphaned_results"]) == 1
    assert len(report["missing_calls"]) == 1


# ---------------------------------------------------------------------------
# 阈值与主流程
# ---------------------------------------------------------------------------


def test_estimate_tokens_charges_cjk_more_than_ascii():
    assert estimate_tokens("中" * 100) > estimate_tokens("a" * 100)
    assert estimate_messages_tokens(_conversation(2)) > 0


def test_should_compress_respects_switch_and_threshold():
    messages = _conversation(6)

    assert CompressionEngine(
        CompactionSettings(), context_length=1_000
    ).should_compress(messages) is True

    disabled = CompressionEngine(CompactionSettings(enabled=False), context_length=1_000)
    assert disabled.should_compress(messages) is False

    tiny = CompressionEngine(CompactionSettings(), context_length=10_000_000)
    assert tiny.should_compress([{"role": "user", "content": "hi"}]) is False


@pytest.mark.asyncio
async def test_compress_skips_below_threshold_without_calling_the_model():
    provider = _FakeProvider()
    engine = CompressionEngine(
        CompactionSettings(), provider=provider, context_length=10_000_000
    )

    result = await engine.compress(
        [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
    )

    assert result.ok is False
    assert result.reason == "below_threshold"
    assert provider.calls == 0


@pytest.mark.asyncio
async def test_compress_replaces_the_middle_with_a_summary():
    provider = _FakeProvider()
    settings = CompactionSettings(protect_first_n=1, protect_last_n=4)
    engine = CompressionEngine(settings, provider=provider, context_length=8_000)
    messages = _conversation(20)

    result = await engine.compress(messages, force=True)

    assert result.ok is True, result.reason
    assert result.summarized_count > 0
    assert len(result.messages) < len(messages)
    # 系统提示保留，并声明历史已被折叠
    assert result.messages[0]["role"] == "system"
    assert COMPRESSION_NOTE.strip() in result.messages[0]["content"]
    body = "\n".join(str(message.get("content") or "") for message in result.messages)
    assert "CONDENSED_SUMMARY" in body
    # 最近的轮次必须原文保留
    assert result.messages[-1]["content"].endswith("a" * CHARS_PER_MESSAGE)
    assert engine.previous_summary == "CONDENSED_SUMMARY"


@pytest.mark.asyncio
async def test_compress_falls_back_to_a_deterministic_summary_on_provider_error():
    provider = _FakeProvider(error=RuntimeError("connection reset by peer"))
    settings = CompactionSettings(protect_first_n=1, protect_last_n=4)
    engine = CompressionEngine(settings, provider=provider, context_length=8_000)

    result = await engine.compress(_conversation(20), force=True)

    assert provider.calls == 1
    assert result.ok is True, result.reason
    assert result.summary_deterministic is True
    # 失败仍要收敛出可用历史，而不是把原历史交给调用方重试
    assert result.messages


@pytest.mark.asyncio
async def test_compress_reports_no_compressible_window():
    provider = _FakeProvider()
    engine = CompressionEngine(
        CompactionSettings(protect_first_n=3, protect_last_n=20),
        provider=provider,
        context_length=8_000,
    )
    # 只有系统提示：没有任何可折叠的历史
    messages = [{"role": "system", "content": "system prompt"}]

    result = await engine.compress(messages, force=True)

    assert result.ok is False
    assert result.reason == "no_compressible_window"
    assert provider.calls == 0
    assert engine.has_content_to_compress(messages) is False
