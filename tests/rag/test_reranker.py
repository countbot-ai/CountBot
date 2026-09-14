"""RerankerClient 单元测试（implementation-plan §8 Phase 2：排序正确 / 失败语义 / 空候选 / 构建）"""

import asyncio
import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.modules.rag.reranker import (
    ENABLED_ENV,
    API_KEY_ENV,
    BASE_URL_ENV,
    RerankerClient,
    build_reranker,
)

CHUNKS = [
    {"chunk_id": f"doc#{i}", "slug": "doc", "doc_title": "文档", "section": f"节{i}",
     "score": 10.0 - i, "content": f"第 {i} 块内容"}   # score 与相关性故意相反：验证按 rerank 分排序
    for i in range(1, 5)
]


def _mock_transport(handler):
    return httpx.MockTransport(handler)


class TestBuildReranker:
    def test_switch_off_returns_none(self, monkeypatch):
        monkeypatch.delenv(ENABLED_ENV, raising=False)
        assert build_reranker() is None

    def test_switch_on_but_unconfigured_returns_none(self, monkeypatch):
        monkeypatch.setenv(ENABLED_ENV, "1")
        monkeypatch.delenv(BASE_URL_ENV, raising=False)
        monkeypatch.delenv(API_KEY_ENV, raising=False)
        assert build_reranker() is None

    def test_fully_configured_builds_client(self, monkeypatch):
        monkeypatch.setenv(ENABLED_ENV, "1")
        monkeypatch.setenv(BASE_URL_ENV, "https://api.example.com/v1")
        monkeypatch.setenv(API_KEY_ENV, "sk-test")
        client = build_reranker()
        assert isinstance(client, RerankerClient)
        assert client.base_url == "https://api.example.com/v1"


class TestRerank:
    def test_empty_chunks_returns_empty(self):
        client = RerankerClient("https://api.example.com/v1", "sk-test")
        assert asyncio.run(client.rerank("q", [])) == []

    def test_sorts_by_relevance_and_truncates_to_top_n(self):
        # relevance 与检索顺序相反：chunk 4 最相关、chunk 1 最不相关
        def handler(request):
            return httpx.Response(200, json={"results": [
                {"index": 3, "relevance_score": 0.91},
                {"index": 2, "relevance_score": 0.55},
                {"index": 1, "relevance_score": 0.12},
                {"index": 0, "relevance_score": 0.01},
            ]})

        client = RerankerClient("https://api.example.com/v1", "sk-test",
                                top_n=2, transport=_mock_transport(handler))
        out = asyncio.run(client.rerank("问题", CHUNKS))

        assert [c["chunk_id"] for c in out] == ["doc#4", "doc#3"]  # 按相关性降序 + 截断 top_n
        assert out[0]["rerank_score"] == pytest.approx(0.91)
        assert out[0]["score"] == pytest.approx(6.0)  # 原检索分保留不动（doc#4 = 10.0 - 4）
        assert out[0]["content"] == "第 4 块内容"      # 其余字段原样带回

    def test_http_error_raises_runtime(self):
        def handler(request):
            return httpx.Response(500, text="boom")

        client = RerankerClient("https://api.example.com/v1", "sk-test",
                                transport=_mock_transport(handler))
        with pytest.raises(RuntimeError, match="HTTP 500"):
            asyncio.run(client.rerank("问题", CHUNKS))

    def test_malformed_response_raises_runtime(self):
        def handler(request):
            return httpx.Response(200, json={"results": [
                {"index": 9, "relevance_score": 0.5},   # 越界 index
            ]})

        client = RerankerClient("https://api.example.com/v1", "sk-test",
                                transport=_mock_transport(handler))
        with pytest.raises(RuntimeError, match="非法"):
            asyncio.run(client.rerank("问题", CHUNKS))

    def test_missing_results_field_raises_runtime(self):
        def handler(request):
            return httpx.Response(200, json={"unexpected": []})

        client = RerankerClient("https://api.example.com/v1", "sk-test",
                                transport=_mock_transport(handler))
        with pytest.raises(RuntimeError, match="results"):
            asyncio.run(client.rerank("问题", CHUNKS))

    def test_payload_contract(self):
        """请求体契约：model/query/documents/top_n（SiliconFlow 风格 /rerank）"""
        captured = {}

        def handler(request):
            captured["url"] = str(request.url)
            captured["auth"] = request.headers.get("Authorization")
            captured["json"] = json.loads(request.content)
            return httpx.Response(200, json={"results": [
                {"index": 0, "relevance_score": 0.5},
            ]})

        client = RerankerClient("https://api.example.com/v1", "sk-test",
                                model="BAAI/bge-reranker-v2-m3",
                                transport=_mock_transport(handler))
        asyncio.run(client.rerank("怎么部署", CHUNKS))

        assert captured["url"] == "https://api.example.com/v1/rerank"
        assert captured["auth"] == "Bearer sk-test"
        body = captured["json"]
        assert body["query"] == "怎么部署"
        assert body["model"] == "BAAI/bge-reranker-v2-m3"
        assert body["top_n"] == 4  # min(top_n=6, len(documents)=4)
        assert len(body["documents"]) == 4
        assert "文档 › 节1" in body["documents"][0]  # 嵌入文本带标题路径上下文
