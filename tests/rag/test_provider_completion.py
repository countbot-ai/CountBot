"""Phase 0 回归测试：LLMProvider.chat_completion（P0 API 断裂修复）

背景：Wiki 链路的 6 处调用点（tool.py 232/336/378/417、api/wiki.py 338/729）
调用了 provider.chat_completion，但基类从未定义该方法——生产环境抛
AttributeError 后被调用方 except Exception 吞掉，CRAG 纠偏与 LLM 生成
静默退化为块列表输出。本文件验证基类便捷方法包裹 chat_stream 的行为：

1. 多个内容块按序拼接；
2. 错误块（StreamChunk.error）以 RuntimeError 抛出；
3. 空流返回空串；
4. prompt 正确包成单条 user 消息，max_tokens / temperature 透传；
5. 非 content 块（usage / finish / reasoning / tool_call）不混入结果。
"""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.modules.providers.base import LLMProvider, StreamChunk


class FakeStreamProvider(LLMProvider):
    """只实现 chat_stream（不自带 chat_completion），
    用于证明所有真实 Provider 均经基类继承获得该方法。"""

    def __init__(self, chunks=None):
        super().__init__()
        self.chunks = list(chunks or [])
        self.calls = []

    async def chat_stream(
        self,
        messages,
        tools=None,
        model=None,
        max_tokens=4096,
        temperature=0.0,
        **kwargs,
    ):
        self.calls.append(
            {
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
        )
        for c in self.chunks:
            yield c

    def get_default_model(self):
        return "fake-model"


class TestChatCompletion:
    def test_concatenates_content_chunks_in_order(self):
        provider = FakeStreamProvider(
            [
                StreamChunk(content="检索质量"),
                StreamChunk(content="评估："),
                StreamChunk(content="all"),
            ]
        )
        out = asyncio.run(provider.chat_completion("评估检索质量"))
        assert out == "检索质量评估：all"

    def test_error_chunk_raises_runtime_error(self):
        provider = FakeStreamProvider(
            [
                StreamChunk(content="部分内容"),
                StreamChunk(error="rate limited"),
            ]
        )
        with pytest.raises(RuntimeError, match="rate limited"):
            asyncio.run(provider.chat_completion("任意问题"))

    def test_empty_stream_returns_empty_string(self):
        provider = FakeStreamProvider([])
        assert asyncio.run(provider.chat_completion("任意问题")) == ""

    def test_wraps_prompt_and_passes_params(self):
        provider = FakeStreamProvider([StreamChunk(content="ok")])
        out = asyncio.run(
            provider.chat_completion("写一句部署说明", max_tokens=3000, temperature=0.7)
        )
        assert out == "ok"
        assert len(provider.calls) == 1
        call = provider.calls[0]
        assert call["messages"] == [{"role": "user", "content": "写一句部署说明"}]
        assert call["max_tokens"] == 3000
        assert call["temperature"] == 0.7

    def test_default_params(self):
        provider = FakeStreamProvider([StreamChunk(content="ok")])
        asyncio.run(provider.chat_completion("任意问题"))
        call = provider.calls[0]
        assert call["max_tokens"] == 2000
        assert call["temperature"] == 0.3

    def test_skips_non_content_chunks(self):
        """usage / finish_reason / reasoning / tool_call 块均无 content，不得混入"""
        provider = FakeStreamProvider(
            [
                StreamChunk(reasoning_content="内心独白"),
                StreamChunk(content="答案"),
                StreamChunk(usage={"total_tokens": 42}),
                StreamChunk(finish_reason="stop"),
            ]
        )
        out = asyncio.run(provider.chat_completion("任意问题"))
        assert out == "答案"


class ScriptedStreamProvider(LLMProvider):
    """按调用顺序返回预设回复的流式 provider。

    与 test_tool_switch.ScriptedProvider 的关键差异：本类**不自带**
    chat_completion，完全依赖基类便捷方法——即真实生产 provider 的形态。
    """

    def __init__(self, replies):
        super().__init__()
        self.replies = list(replies)
        self.calls = []

    async def chat_stream(self, messages, tools=None, model=None,
                          max_tokens=4096, temperature=0.0, **kwargs):
        prompt = messages[0]["content"]
        self.calls.append(prompt)
        if not self.replies:
            yield StreamChunk(content="DEFAULT")
            return
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            yield StreamChunk(error=str(reply))
            return
        # 拆成两个块返回，同时验证流式拼接
        mid = max(1, len(reply) // 2)
        yield StreamChunk(content=reply[:mid])
        yield StreamChunk(content=reply[mid:])

    def get_default_model(self):
        return "fake-model"


class TestProductionWiring:
    """P0 修复的生产链路证明：WikiTool._rag_ask 经基类 chat_completion 走通 grader → 生成。

    修复前，这类 provider 会在 6 处调用点抛 AttributeError 并被吞掉，
    ask 恒回退到块列表输出（matching sections）。
    """

    def test_rag_ask_grades_and_generates_via_base_method(
        self, tmp_path, monkeypatch
    ):
        import frontmatter
        import types

        concepts = tmp_path / "concepts"
        concepts.mkdir(parents=True)
        post = frontmatter.Post("使用 docker-compose 一键启动，命令为 docker compose up -d。\n")
        post.metadata["title"] = "部署指南"
        post.metadata["tags"] = ["ops"]
        (concepts / "deploy.md").write_text(frontmatter.dumps(post), encoding="utf-8")

        provider = ScriptedStreamProvider([
            '{"grade": "all", "relevant": [1, 2]}',  # grader
            "ANSWER_OK",                              # 生成
        ])
        fake_app = types.ModuleType("backend.app")
        fake_app.get_shared_provider = lambda: provider
        monkeypatch.setitem(sys.modules, "backend.app", fake_app)
        monkeypatch.setenv("COUNTBOT_RAG_CHUNKS", "1")

        from backend.modules.wiki.tool import WikiTool

        tool = WikiTool(tmp_path)
        out = asyncio.run(tool._handle_ask("如何用 Docker 部署"))

        assert out == "ANSWER_OK"  # LLM 生成，而非块列表回退
        assert "matching sections" not in out
        assert len(provider.calls) == 2  # 评估 1 次 + 生成 1 次
        assert "检索质量评估器" in provider.calls[0]
        assert "docker-compose" in provider.calls[1]
