"""M2 嵌入客户端回归测试（Phase 1 任务 2）

覆盖点（implementation-plan §8）：Noop 降级 / 批量切分 / 维度校验，
另补：index 乱序归位 / HTTP 错误传播 / 响应条数校验 / 空输入。

降级安全是本模块的核心契约：未配置环境变量时 build_embedding_client()
必须返回 None，上层据此回落纯 BM25（行为与现状完全一致）。
"""

import asyncio
import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.modules.rag.embeddings import (
    API_KEY_ENV,
    BASE_URL_ENV,
    BATCH_SIZE,
    DIM_ENV,
    MODEL_ENV,
    EmbeddingClient,
    build_embedding_client,
)

DIM = 4  # 测试用小维度


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """四个环境变量全部清零，防止宿主环境污染用例"""
    for var in (BASE_URL_ENV, API_KEY_ENV, MODEL_ENV, DIM_ENV):
        monkeypatch.delenv(var, raising=False)


def make_transport(dim=DIM, status=200, records=None, scramble=True):
    """MockTransport：记录请求；embedding 向量 = [index]*dim，可乱序返回

    向量取值即 index，使「按 index 归位」的正确性可直接断言：
    归位正确则 out[i] == [i]*dim。
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if records is not None:
            records.append(json.loads(request.content))
        payload = json.loads(request.content)
        n = len(payload["input"])
        indexes = list(range(n - 1, -1, -1)) if scramble else list(range(n))
        data = [
            {"object": "embedding", "index": i, "embedding": [float(i)] * dim}
            for i in indexes
        ]
        return httpx.Response(status, json={"data": data, "model": payload["model"]})

    return httpx.MockTransport(handler)


def make_client(transport, **kwargs):
    return EmbeddingClient(
        "https://embed.example.com/v1", "sk-test", dim=DIM,
        transport=transport, **kwargs
    )


class TestBuildClient:
    def test_returns_none_when_unconfigured(self):
        assert build_embedding_client() is None

    def test_returns_none_when_only_base_url(self, monkeypatch):
        monkeypatch.setenv(BASE_URL_ENV, "https://embed.example.com/v1")
        assert build_embedding_client() is None

    def test_returns_none_when_only_api_key(self, monkeypatch):
        monkeypatch.setenv(API_KEY_ENV, "sk-test")
        assert build_embedding_client() is None

    def test_reads_env_with_defaults(self, monkeypatch):
        monkeypatch.setenv(BASE_URL_ENV, "https://embed.example.com/v1/")
        monkeypatch.setenv(API_KEY_ENV, "sk-test")
        client = build_embedding_client()
        assert client is not None
        assert client.base_url == "https://embed.example.com/v1"  # 去尾斜杠
        assert client.model == "BAAI/bge-m3"
        assert client.dim == 1024

    def test_reads_env_overrides(self, monkeypatch):
        monkeypatch.setenv(BASE_URL_ENV, "https://x.example.com/v1")
        monkeypatch.setenv(API_KEY_ENV, "sk-test")
        monkeypatch.setenv(MODEL_ENV, "text-embedding-3-small")
        monkeypatch.setenv(DIM_ENV, "1536")
        client = build_embedding_client()
        assert client.model == "text-embedding-3-small"
        assert client.dim == 1536

    def test_invalid_dim_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv(BASE_URL_ENV, "https://x.example.com/v1")
        monkeypatch.setenv(API_KEY_ENV, "sk-test")
        monkeypatch.setenv(DIM_ENV, "not-a-number")
        assert build_embedding_client().dim == 1024


class TestEmbedTexts:
    def test_empty_input_returns_empty(self):
        client = make_client(make_transport())
        assert asyncio.run(client.embed_texts([])) == []

    def test_batches_capped_at_16(self):
        records = []
        client = make_client(make_transport(records=records))
        texts = [f"chunk-{i}" for i in range(40)]  # 40 → 16 + 16 + 8

        out = asyncio.run(client.embed_texts(texts))

        assert [len(r["input"]) for r in records] == [16, 16, 8]
        assert all(r["model"] == "BAAI/bge-m3" for r in records)
        # 输入顺序完整保留（跨批拼接）
        assert [r["input"] for r in records] == [texts[:16], texts[16:32], texts[32:]]
        assert len(out) == 40

    def test_output_ordered_by_index_despite_scrambled_response(self):
        """响应 data 乱序（index 倒序）时，必须按 index 归位"""
        client = make_client(make_transport(scramble=True))
        out = asyncio.run(client.embed_texts(["a", "b", "c"]))
        assert out == [[0.0] * DIM, [1.0] * DIM, [2.0] * DIM]

    def test_query_single_text(self):
        client = make_client(make_transport())
        vec = asyncio.run(client.embed_query("查询"))
        assert vec == [0.0] * DIM

    def test_http_error_raises_runtime_error(self):
        client = make_client(make_transport(status=500))
        with pytest.raises(RuntimeError, match="HTTP 500"):
            asyncio.run(client.embed_texts(["a"]))

    def test_count_mismatch_raises_runtime_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": []})  # 期望 2 条，实给 0

        client = make_client(httpx.MockTransport(handler))
        with pytest.raises(RuntimeError, match="条数不符"):
            asyncio.run(client.embed_texts(["a", "b"]))

    def test_dimension_mismatch_raises_value_error(self):
        client = make_client(make_transport(dim=DIM + 1))
        with pytest.raises(ValueError, match="维度不符"):
            asyncio.run(client.embed_texts(["a"]))

    def test_missing_index_raises_runtime_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            data = [
                {"object": "embedding", "index": 0, "embedding": [0.0] * DIM}
                for _ in payload["input"]
            ]
            if len(data) > 1:
                data[1].pop("index")  # 缺 index → 无法归位
            return httpx.Response(200, json={"data": data})

        client = make_client(httpx.MockTransport(handler))
        with pytest.raises(RuntimeError, match="index 缺失"):
            asyncio.run(client.embed_texts(["a", "b"]))
    def test_batch_size_constant(self):
        """规格锚点：input 批量上限 ≤16（implementation-plan §5 任务 2）"""
        assert BATCH_SIZE == 16
