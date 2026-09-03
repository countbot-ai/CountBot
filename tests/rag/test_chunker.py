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
