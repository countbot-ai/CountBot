"""会话历史压缩测试

重点覆盖切点安全性：任何情况下都不能把工具调用与其结果切开，
否则请求里会出现孤儿 tool_calls。
"""

import pytest

from backend.modules.agent.history_compactor import (
    HistoryCompactor,
    find_cut_index,
    is_safe_cut_point,
    should_compress,
    split_for_summary,
)


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
                    "function": {"name": "read_file", "arguments": "{}"},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": call_id,
            "name": "read_file",
            "content": "file body",
        },
    ]


def test_should_compress_threshold():
    assert should_compress([{}] * 15, threshold=15) is False
    assert should_compress([{}] * 16, threshold=15) is True


def test_keep_cannot_start_with_tool_result():
    """保留段以 tool 结果开头时不可切。"""
    messages = [
        {"role": "user", "content": "hi"},
        *_tool_turn(),
        {"role": "user", "content": "next"},
    ]
    # index=2 是 tool 结果，不可作为起点
    assert is_safe_cut_point(messages, 2) is False
    # index=1 是 assistant(tool_calls)，可作为起点（工具对完整保留）
    assert is_safe_cut_point(messages, 1) is True


def test_cut_index_avoids_splitting_tool_pair():
    """期望保留 2 条时若会切断工具对，应向安全方向调整。"""
    messages = [{"role": "user", "content": f"m{i}"} for i in range(5)]
    messages += _tool_turn()
    messages += [{"role": "user", "content": "tail"}]

    cut = find_cut_index(messages, min_keep_recent=2)
    assert is_safe_cut_point(messages, cut)
    kept = messages[cut:]
    # 保留段内不允许出现孤立的 tool 结果
    if kept and kept[0].get("role") == "tool":
        pytest.fail("kept segment must not start with a tool result")


def test_split_returns_empty_when_no_safe_point():
    """全部消息都是工具结果时无法安全切分，应放弃压缩。"""
    messages = [{"role": "tool", "content": "x"} for _ in range(5)]
    to_summarize, to_keep = split_for_summary(messages, min_keep_recent=2)
    assert to_summarize == []
    assert len(to_keep) == 5


def test_split_keeps_recent_and_summarizes_rest():
    messages = [{"role": "user", "content": f"m{i}"} for i in range(10)]
    to_summarize, to_keep = split_for_summary(messages, min_keep_recent=4)
    assert len(to_keep) == 4
    assert len(to_summarize) == 6
    assert to_keep[0]["content"] == "m6"


def test_find_cut_index_edge_cases():
    assert find_cut_index([], min_keep_recent=3) == 0

    single = [{"role": "user", "content": "only"}]
    cut = find_cut_index(single, min_keep_recent=5)
    assert cut == 0  # 保留数超过总数，无需切分


class _FakeChunk:
    def __init__(self, content: str):
        self.content = content
        self.is_content = True


class _FakeProvider:
    """最小化的 provider 替身，返回固定摘要。"""

    def __init__(self, summary: str = "用户要求读取文件，已读取 3 个。"):
        self.summary = summary
        self.calls = 0

    async def chat_stream(self, messages, tools=None, max_tokens=4096, **kwargs):
        self.calls += 1
        yield _FakeChunk(self.summary)


@pytest.mark.asyncio
async def test_compress_produces_summary_plus_tail():
    provider = _FakeProvider()
    compactor = HistoryCompactor(provider=provider, min_keep_recent=3, threshold=5)
    # 用有实际体量的内容：压缩后必须真的变短，否则会被 no_reduction 拒绝
    messages = [
        {"role": "user", "content": f"第 {i} 条消息，包含足够的上下文内容用于压缩验证。" * 20}
        for i in range(8)
    ]

    result = await compactor.compress(messages)

    assert result is not None
    assert result[0]["role"] == "system"
    assert "Previous Conversation Summary" in result[0]["content"]
    assert len(result) == 4  # 1 条摘要 + 3 条原文
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_compress_skips_below_threshold():
    provider = _FakeProvider()
    compactor = HistoryCompactor(provider=provider, min_keep_recent=3, threshold=15)
    result = await compactor.compress([{"role": "user", "content": "hi"}])
    assert result is None
    assert provider.calls == 0


@pytest.mark.asyncio
async def test_compress_returns_none_when_summary_missing():
    provider = _FakeProvider(summary="   ")
    compactor = HistoryCompactor(provider=provider, min_keep_recent=3, threshold=5)
    messages = [{"role": "user", "content": f"m{i}"} for i in range(8)]
    assert await compactor.compress(messages) is None


@pytest.mark.asyncio
async def test_compress_survives_provider_error():
    class _BrokenProvider:
        async def chat_stream(self, *args, **kwargs):
            raise RuntimeError("upstream down")
            yield  # pragma: no cover

    compactor = HistoryCompactor(provider=_BrokenProvider(), min_keep_recent=3, threshold=5)
    messages = [{"role": "user", "content": f"m{i}"} for i in range(8)]
    # 摘要失败不应影响主流程，调用方沿用原历史
    assert await compactor.compress(messages) is None


def test_strip_preamble():
    assert HistoryCompactor._strip_preamble("以下是对话摘要：用户要读文件") == "用户要读文件"
    assert HistoryCompactor._strip_preamble("用户要读文件") == "用户要读文件"
    assert HistoryCompactor._strip_preamble("") == ""

@pytest.mark.asyncio
async def test_oversized_summary_is_rejected():
    """摘要超过上限时放弃压缩，而不是把更长的摘要塞进上下文。

    模型偶尔不遵守「简短」指令；若不设上限，压缩会让上下文变长，
    完全违背压缩目的。
    """
    class _HugeProvider:
        async def chat_stream(self, *args, **kwargs):
            class _C:
                is_content = True
                content = "摘要" * 100000
            yield _C()

    compactor = HistoryCompactor(
        provider=_HugeProvider(), min_keep_recent=3, threshold=5, summary_max_chars=4000
    )
    messages = [{"role": "user", "content": f"m{i}"} for i in range(10)]

    assert await compactor.compress(messages) is None


@pytest.mark.asyncio
async def test_normal_summary_still_compresses():
    """上限不能误伤正常摘要。"""
    compactor = HistoryCompactor(
        provider=_FakeProvider("简短摘要"), min_keep_recent=3, threshold=5
    )
    messages = [{"role": "user", "content": f"m{i}"} for i in range(10)]

    result = await compactor.compress(messages)
    assert result is not None
    assert "简短摘要" in result[0]["content"]

# ---------------------------------------------------------------------------
# token 级触发与结构化结果（对标生产级压缩系统）
# ---------------------------------------------------------------------------


def test_estimate_tokens_handles_cjk_and_ascii():
    from backend.modules.agent.history_compactor import estimate_tokens

    # 中文按 1 字 1 token，英文按 4 字符 1 token
    assert estimate_tokens("中文内容") == 4
    assert estimate_tokens("abcdefgh") == 2
    assert estimate_tokens("") == 0
    assert estimate_tokens(None or "") == 0


def test_estimate_messages_tokens_counts_structure():
    from backend.modules.agent.history_compactor import estimate_messages_tokens

    one = estimate_messages_tokens([{"role": "user", "content": "hi"}])
    # 至少包含 role/分隔符的结构开销
    assert one >= 4


def test_estimate_tokens_with_tool_calls():
    from backend.modules.agent.history_compactor import estimate_messages_tokens

    msgs = [
        {
            "role": "assistant",
            "content": "ok",
            "tool_calls": [
                {"function": {"name": "read_file", "arguments": '{"path":"a.txt"}'}}
            ],
        }
    ]
    assert estimate_messages_tokens(msgs) > 10


def test_should_compress_triggers_on_token_threshold():
    """token 超阈值即触发，即使条数很少。

    这是判据换成 token 的核心价值：一条超长消息也应触发压缩。
    """
    from backend.modules.agent.history_compactor import should_compress

    # 2 条消息，但内容极长
    big = [{"role": "user", "content": "很长内容" * 100000}]
    assert should_compress(big, threshold=15, token_threshold=1000) is True


def test_should_compress_falls_back_to_count_without_token_threshold():
    """未给 token 阈值时保持旧的条数行为，兼容既有调用方。"""
    from backend.modules.agent.history_compactor import should_compress

    msgs = [{"role": "user", "content": "x"} for _ in range(20)]
    assert should_compress(msgs, threshold=15) is True
    assert should_compress(msgs[:10], threshold=15) is False


@pytest.mark.asyncio
async def test_compress_with_detail_reports_reduction():
    """成功的压缩要给出版前后 token 与节省量。"""
    compactor = HistoryCompactor(provider=_FakeProvider("简短摘要"), min_keep_recent=3, threshold=5)
    messages = [
        {"role": "user", "content": "第 {} 条，包含足够内容用于压缩验证。".format(i) * 30}
        for i in range(10)
    ]

    result = await compactor.compress_with_detail(messages)

    assert result.ok is True
    assert result.reason == "ok"
    assert result.before_tokens > result.after_tokens
    assert result.saved_tokens > 0
    assert result.messages is not None


@pytest.mark.asyncio
async def test_compress_with_detail_reports_below_threshold():
    """未达阈值时给出明确原因，而不是笼统的 None。"""
    compactor = HistoryCompactor(provider=_FakeProvider(), min_keep_recent=3, threshold=50)
    result = await compactor.compress_with_detail([{"role": "user", "content": "hi"}])

    assert result.ok is False
    assert result.reason == "below_threshold"


@pytest.mark.asyncio
async def test_compress_with_detail_reports_summary_failure():
    class _Broken:
        async def chat_stream(self, *args, **kwargs):
            raise RuntimeError("down")
            yield

    compactor = HistoryCompactor(provider=_Broken(), min_keep_recent=3, threshold=5)
    messages = [{"role": "user", "content": "内容" * 200} for _ in range(10)]
    result = await compactor.compress_with_detail(messages)

    assert result.ok is False
    assert result.reason == "summary_failed"


@pytest.mark.asyncio
async def test_compress_with_detail_rejects_no_reduction():
    """压缩后没变短时应拒绝，而不是接受一个更长的结果。"""
    class _Verbose:
        async def chat_stream(self, *args, **kwargs):
            class _C:
                is_content = True
                # 摘要比原文还长
                content = "啰嗦摘要" * 5000
            yield _C()

    compactor = HistoryCompactor(
        provider=_Verbose(), min_keep_recent=2, threshold=5, summary_max_chars=100000
    )
    messages = [{"role": "user", "content": "短"} for _ in range(10)]

    result = await compactor.compress_with_detail(messages)
    assert result.ok is False
    assert result.reason in {"no_reduction", "summary_too_long"}
