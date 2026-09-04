"""M1 分块检索单元测试：chunker + ChunkedBM25Index"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.modules.rag.chunker import HeadingChunker
from backend.modules.rag.stores import ChunkedBM25Index


SAMPLE = """# 部署指南

介绍如何部署 CountBot。

## 环境要求

- Python 3.10+
- Node.js 18+

## Docker 部署

使用 docker-compose 一键启动。

```bash
docker compose up -d
```

代码块内的 `#` 不应被识别为标题。

## 数据库

默认使用 SQLite，文件为 countbot.db。
"""


class TestHeadingChunker:
    def test_sections_split_by_heading(self):
        chunks = HeadingChunker().chunk("deploy", "部署", SAMPLE)
        sections = [c.section for c in chunks]
        assert any("环境要求" in s for s in sections)
        assert any("Docker 部署" in s for s in sections)
        assert any("数据库" in s for s in sections)

    def test_heading_path_hierarchy(self):
        chunks = HeadingChunker().chunk("deploy", "部署", SAMPLE)
        docker = next(c for c in chunks if "Docker" in c.section)
        assert docker.heading_path == "部署指南 > Docker 部署"

    def test_chunk_id_traceable(self):
        chunks = HeadingChunker().chunk("deploy", "部署", SAMPLE)
        for c in chunks:
            assert c.chunk_id.startswith("deploy#"), c.chunk_id

    def test_fence_hash_not_heading(self):
        chunks = HeadingChunker().chunk("deploy", "部署", SAMPLE)
        docker = next(c for c in chunks if "Docker" in c.section)
        assert "代码块内的" in docker.content
        assert "docker compose up -d" in docker.content

    def test_long_section_split_with_limit(self):
        long_section = "## 长节\n\n" + "\n\n".join(f"段落 {i}。" + "内容" * 100 for i in range(30))
        chunks = HeadingChunker(max_chars=1200).chunk("doc", "t", long_section)
        assert len(chunks) > 1
        assert all(len(c.content) <= 1400 for c in chunks)  # 上限 + 少量 overlap

    def test_index_title_composition(self):
        chunks = HeadingChunker().chunk("deploy", "部署指南", SAMPLE)
        docker = next(c for c in chunks if "Docker" in c.section)
        assert "部署指南" in docker.index_title
        assert "Docker" in docker.index_title


class TestChunkedBM25Index:
    def _build(self):
        store = ChunkedBM25Index()
        store.add_document("deploy", "部署指南", SAMPLE, ["ops"])
        store.add_document("memory", "记忆系统", "# 记忆\n\n记忆存在 memory.md 文件。\n", ["core"])
        return store

    def test_search_hits_section(self):
        store = self._build()
        results = store.search_chunks("Docker 部署", top_k=3)
        assert results
        assert results[0]["slug"] == "deploy"
        assert "Docker" in results[0]["section"]

    def test_result_traceability(self):
        store = self._build()
        for r in store.search_chunks("环境要求", top_k=5):
            assert r["chunk_id"].startswith(("deploy#", "memory#"))

    def test_remove_document(self):
        store = self._build()
        store.remove_document("deploy")
        assert all(r["slug"] != "deploy" for r in store.search_chunks("Docker 部署", top_k=5))

    def test_readd_updates_chunks(self):
        store = self._build()
        before = store.stats()["total_chunks"]
        store.add_document("deploy", "部署指南", "# 部署\n\n只有一节。\n", ["ops"])
        assert store.stats()["total_chunks"] < before
        # 旧 Docker 内容必须已被替换（不再出现在任何块中）
        for r in store.search_chunks("Docker 部署", top_k=5):
            assert "docker compose" not in r["content"]

    def test_persistence_roundtrip(self, tmp_path):
        store = self._build()
        f = tmp_path / "chunk_index.json"
        store.save_to_file(str(f))
        store2 = ChunkedBM25Index()
        assert store2.load_from_file(str(f))
        r = store2.search_chunks("Docker 部署", top_k=3)
        assert r and r[0]["slug"] == "deploy"
        assert store2.stats()["total_chunks"] == store.stats()["total_chunks"]


class TestMaxPerDoc:
    """max_per_doc：同一文档的多个高分块不得挤占前排（跨文档多样性），
    且凑不满 top_k 时按分数回填（小知识库不丢结果）"""

    LONG_DEPLOY = "# 部署指南\n\n" + "\n\n".join(
        f"## 部署阶段{i}\n\nDocker 部署阶段{i}的完整流程：拉取镜像、配置环境变量、启动容器并验证服务健康。"
        for i in range(1, 9)
    )

    def _build(self):
        store = ChunkedBM25Index()
        store.add_document("deploy", "部署指南", self.LONG_DEPLOY, ["ops"])
        store.add_document("memory", "记忆系统", "# 记忆的部署\n\nDocker 部署完成后，记忆存储在本地文件中。\n", ["core"])
        return store

    @pytest.fixture(autouse=True)
    def _no_abs_threshold(self, monkeypatch):
        """本测试语料极小（9 块且多数含查询词），BM25 的 IDF 会塌缩，
        绝对阈值 SCORE_THRESHOLD 会把所有块滤光。本组测试只关心
        per-doc 截断逻辑，显式关闭绝对阈值。"""
        from backend.modules.wiki.index import BM25Index
        monkeypatch.setattr(BM25Index, "SCORE_THRESHOLD", 0.0)

    def test_max_per_doc_caps_front_of_results(self):
        """前排遵守 cap：结果前段中同一文档不超过 max_per_doc 块"""
        store = self._build()
        uncapped = store.search_chunks("Docker 部署", top_k=10, max_per_doc=0)
        assert sum(1 for r in uncapped if r["slug"] == "deploy") > 2

        capped = store.search_chunks("Docker 部署", top_k=10, max_per_doc=2)
        assert capped, "截断后不应为空"
        # 前排 = 每文档先各取 cap 块（deploy 2 + memory 1 = 3 个位置）
        front = capped[:3]
        assert sum(1 for r in front if r["slug"] == "deploy") <= 2

    def test_backfill_keeps_result_count(self):
        """文档数不足时回填：结果数不缩水（小知识库零损失）"""
        store = ChunkedBM25Index()
        store.add_document("deploy", "部署指南", self.LONG_DEPLOY, ["ops"])
        results = store.search_chunks("Docker 部署", top_k=6, max_per_doc=1)
        assert len(results) == 6, "单文档库也必须凑满 top_k"
        # 首位是最高分块；其余为回填
        assert results[0]["slug"] == "deploy"

    def test_max_per_doc_zero_disables_cap(self):
        """max_per_doc=0（或负数）= 完全回退到旧行为（不截断）"""
        store = self._build()
        legacy = store.search("Docker 部署", top_k=10, max_per_doc=0)
        direct = store._bm25.search("Docker 部署", top_k=10, min_score_ratio=0.3)
        assert [c for c, _ in legacy] == [c for c, _ in direct]

    def test_top_k_respected_with_cap(self):
        store = self._build()
        results = store.search_chunks("Docker 部署", top_k=3, max_per_doc=2)
        assert len(results) <= 3
        # 分数仍按降序排列（截断与回填都不破坏排序语义）
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)
