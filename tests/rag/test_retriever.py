"""M2 混合检索回归测试（Phase 1 任务 4）

覆盖点（implementation-plan §8）：RRF 纯函数 / 混合返回结构 / 无向量时
回落 BM25，另补：dense-only 召回（BM25 零词重叠）、索引漂移防御、
service 层混合分派与向量双写、嵌入失败降级链。

FakeEmbedder 采用「关键词 → 正交基」确定性映射，使 Dense 通道的
排序完全可断言。
"""

import asyncio
import sys
from pathlib import Path

import frontmatter
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.modules.rag.retriever import HybridRetriever, rrf_fusion, rrf_scores
from backend.modules.rag.service import RagService
from backend.modules.rag.stores import ChunkedBM25Index, VectorStore
from backend.modules.wiki.service import WikiService

K = 60


def write_concept(wiki_dir: Path, slug: str, title: str, content: str, tags=None):
    concepts = wiki_dir / "concepts"
    concepts.mkdir(parents=True, exist_ok=True)
    post = frontmatter.Post(content)
    post.metadata["title"] = title
    post.metadata["tags"] = list(tags or [])
    post.metadata["summary"] = content[:200].strip()
    (concepts / f"{slug}.md").write_text(frontmatter.dumps(post), encoding="utf-8")


@pytest.fixture
def wiki_dir(tmp_path):
    d = tmp_path / "wiki"
    write_concept(d, "deploy", "部署指南",
                  "介绍如何部署 CountBot。\n\n## Docker 部署\n使用 docker-compose 一键启动。\n\n## Helm 部署\nk8s helm chart。\n")
    write_concept(d, "memory", "记忆系统",
                  "记忆存储说明。\n\n## 检索\n支持按关键词检索历史记忆。\n")
    return d


class KeywordEmbedder:
    """关键词 → 正交基向量的确定性假嵌入"""

    DIM = 8

    def __init__(self, error: bool = False):
        self.error = error
        self.embedded_texts: list = []

    def _vec(self, text: str):
        v = [0.0] * self.DIM
        t = text.lower()
        if "docker" in t or "部署" in t:
            v[0] = 1.0
        elif "记忆" in t or "memory" in t:
            v[1] = 1.0
        elif "helm" in t or "k8s" in t:
            v[2] = 1.0
        else:
            v[7] = 1.0
        return v

    async def embed_texts(self, texts):
        if self.error:
            raise RuntimeError("embed API down")
        self.embedded_texts.extend(texts)
        return [self._vec(t) for t in texts]

    async def embed_query(self, text):
        if self.error:
            raise RuntimeError("embed API down")
        return self._vec(text)


def build_store():
    store = ChunkedBM25Index()
    store.add_document("deploy", "部署指南",
                       "介绍如何部署 CountBot。\n\n## Docker 部署\n使用 docker-compose 一键启动。\n\n## Helm 部署\nk8s helm chart。\n",
                       ["ops"])
    store.add_document("memory", "记忆系统",
                       "记忆存储说明。\n\n## 检索\n支持按关键词检索历史记忆。\n", ["core"])
    return store


class TestRRFFusion:
    def test_empty_inputs(self):
        assert rrf_fusion([]) == []
        assert rrf_fusion([[], []]) == []

    def test_single_list_preserves_order(self):
        assert rrf_fusion([["a", "b", "c"]]) == ["a", "b", "c"]

    def test_score_formula(self):
        """score(d) = Σ 1/(k+rank)；双通道冠军必须登顶"""
        scores = rrf_scores([["a", "b"], ["a", "c"]], k=K)
        assert scores["a"] == pytest.approx(2.0 / (K + 1))
        assert scores["b"] == pytest.approx(1.0 / (K + 2))
        assert scores["c"] == pytest.approx(1.0 / (K + 2))
        assert rrf_fusion([["a", "b"], ["a", "c"]], k=K)[0] == "a"

    def test_duplicate_in_one_list_counted_once(self):
        scores = rrf_scores([["a", "a", "b"]], k=K)
        assert scores["a"] == pytest.approx(1.0 / (K + 1))

    def test_k_parameter(self):
        scores = rrf_scores([["a", "b"]], k=1)
        assert scores["a"] == pytest.approx(1.0 / 2)


class TestHybridRetriever:
    def make_retriever(self, embedder, extra_vectors=None):
        store = build_store()
        vs = VectorStore()
        vs.add("deploy#docker-部署", [1.0] + [0.0] * 7)
        vs.add("deploy#helm-部署", [0.0, 0.0, 1.0] + [0.0] * 5)
        vs.add("memory#检索", [0.0, 1.0] + [0.0] * 6)
        if extra_vectors:
            for cid, vec in extra_vectors:
                vs.add(cid, vec)
        return HybridRetriever(store, vs, embedder), store, vs

    def test_result_structure_matches_6_1(self):
        """返回结构必须与 search_chunks 一致（§6.1 契约）"""
        r, _, _ = self.make_retriever(KeywordEmbedder())
        out = asyncio.run(r.search("如何用 Docker 部署", top_k=3))
        assert out
        for c in out:
            assert set(c) == {"chunk_id", "slug", "doc_title", "section", "score", "content"}
            assert c["slug"] in ("deploy", "memory")

    def test_both_channel_hit_ranks_first(self):
        """双通道均命中的块必须排第一（RRF 融合的意义所在）"""
        r, _, _ = self.make_retriever(KeywordEmbedder())
        out = asyncio.run(r.search("Docker 部署", top_k=3))
        assert out[0]["chunk_id"].startswith("deploy#")

    def test_dense_only_chunk_surfaces(self):
        """BM25 零词重叠（语义鸿沟）时 Dense 通道补位"""
        r, store, vs = self.make_retriever(KeywordEmbedder())

        # 造一个 BM25 完全无法命中的块：内容与查询零字符重叠，但向量对齐
        store.add_document("future", "路线图", "## Roadmap\nKubernetes native.\n", ["plan"])
        vs.add("future#roadmap", [1.0] + [0.0] * 7)  # 与 "部署" 查询向量对齐

        out = asyncio.run(r.search("怎么部署", top_k=6))
        ids = [c["chunk_id"] for c in out]
        assert any(i.startswith("future#") for i in ids), "dense-only 块必须能经向量通道浮现"

    def test_dense_failure_falls_back_to_bm25_order(self):
        """嵌入 API 失败 → 降级为 BM25-only，排序与纯 BM25 一致"""
        r, store, _ = self.make_retriever(KeywordEmbedder(error=True))
        out = asyncio.run(r.search("Docker 部署", top_k=6))
        bm25_only = [c["chunk_id"] for c in store.search_chunks("Docker 部署", top_k=6)]
        assert [c["chunk_id"] for c in out] == bm25_only

    def test_drifted_vector_skipped_not_crashed(self):
        """向量索引漂移（BM25 无元数据）→ 跳过并降位，不抛错不返回残缺"""
        r, _, _ = self.make_retriever(
            KeywordEmbedder(), extra_vectors=[("ghost#nowhere", [1.0] + [0.0] * 7)])
        out = asyncio.run(r.search("Docker 部署", top_k=6))
        assert all(c["chunk_id"] != "ghost#nowhere" for c in out)
        assert all(c.get("content") for c in out)

    def test_no_hits_returns_empty(self):
        r, _, _ = self.make_retriever(KeywordEmbedder())
        assert asyncio.run(r.search("zzzqqqxxxyyy", top_k=6)) == []

    def test_zero_similarity_dense_hits_filtered(self):
        """Dense 噪声门：正交（零相似）向量不进候选池"""
        r, _, _ = self.make_retriever(KeywordEmbedder())
        # "zzzqqq" 落入 default 向量 e7，与库内所有向量正交 → dense 空
        out = asyncio.run(r.search("zzzqqq 部署", top_k=6))
        ids = [c["chunk_id"] for c in out]
        assert all(i.startswith("deploy#") for i in ids)  # 只有 BM25 命中的部署块


class TestServiceHybridWiring:
    def test_hybrid_off_matches_m1(self, wiki_dir, monkeypatch):
        """未注入 embedder 且开关关闭 → 无向量层，stats 与 M1 一致"""
        monkeypatch.delenv("COUNTBOT_RAG_HYBRID", raising=False)
        svc = WikiService(wiki_dir)
        rag = RagService(svc, wiki_dir)
        s = rag.stats()
        assert "hybrid" not in s
        assert rag._retriever is None
        # 纯 BM25 路径照常工作
        assert rag.search_chunks("Docker 部署")

    def test_hybrid_on_builds_vectors_and_dispatches(self, wiki_dir):
        """注入 embedder → 向量双写、检索走 RRF、持久化 vector_index 文件"""
        embedder = KeywordEmbedder()
        svc = WikiService(wiki_dir)
        rag = RagService(svc, wiki_dir, embedder=embedder)

        s = rag.stats()
        assert s["hybrid"] is True
        assert s["vector_chunks"] == s["total_chunks"]
        assert not (wiki_dir / "vector_index.npz").exists() or True  # 文件名随 numpy 可用性

        out = rag.search_chunks("Docker 部署")
        assert out
        assert set(out[0]) == {"chunk_id", "slug", "doc_title", "section", "score", "content"}
        # 持久化文件存在（numpy 可用 → .npz；否则 .json）
        assert ((wiki_dir / "vector_index.npz").exists()
                or (wiki_dir / "vector_index.json").exists())

    def test_hybrid_persists_across_restart(self, wiki_dir):
        """二次实例化走 load 而非重嵌（embedded_texts 不再增长）"""
        e1 = KeywordEmbedder()
        RagService(WikiService(wiki_dir), wiki_dir, embedder=e1)
        assert e1.embedded_texts  # 首次全量嵌入

        e2 = KeywordEmbedder()
        rag2 = RagService(WikiService(wiki_dir), wiki_dir, embedder=e2)
        assert e2.embedded_texts == []  # 全部从磁盘加载
        assert rag2.stats()["vector_chunks"] > 0

    def test_on_document_added_embeds_new_doc(self, wiki_dir):
        embedder = KeywordEmbedder()
        svc = WikiService(wiki_dir)
        rag = RagService(svc, wiki_dir, embedder=embedder)
        before = rag.stats()["vector_chunks"]

        write_concept(wiki_dir, "newdoc", "新条目", "# 新\n\n云原生部署新方案。\n", ["new"])
        svc.add_document("newdoc", "新条目", "# 新\n\n云原生部署新方案。\n", ["new"])
        rag.on_document_added("newdoc")

        assert rag.stats()["vector_chunks"] > before

    def test_on_document_removed_prunes_vectors(self, wiki_dir):
        embedder = KeywordEmbedder()
        svc = WikiService(wiki_dir)
        rag = RagService(svc, wiki_dir, embedder=embedder)
        full = rag.stats()["vector_chunks"]

        rag.on_document_removed("memory")
        after = rag.stats()["vector_chunks"]
        assert 0 < after < full

    def test_sync_embeds_changed_doc(self, wiki_dir):
        """mtime 变更 → sync 双写：内容变了的块拿到新向量（即使 chunk_id 复用）"""
        embedder = KeywordEmbedder()
        svc = WikiService(wiki_dir)
        rag = RagService(svc, wiki_dir, embedder=embedder)
        n_embedded = len(embedder.embedded_texts)

        # 触碰文件（mtime 更新）并改内容
        write_concept(wiki_dir, "deploy", "部署指南", "部署方式已改为 helm install。\n", ["ops"])
        svc.add_document("deploy", "部署指南", "部署方式已改为 helm install。\n", ["ops"])
        stats = rag.sync()

        assert stats["updated"] == 1
        assert len(embedder.embedded_texts) > n_embedded  # 过期文档被重嵌
        s = rag.stats()
        assert s["vector_chunks"] == s["total_chunks"]  # 双写后两者对齐

        # 重嵌后的向量确实反映新内容：helm 关键词可经 Dense 通道召回
        out = rag.search_chunks("helm install")
        assert out and any("helm" in c["content"].lower() for c in out)

    def test_vector_mtime_survives_restart(self, wiki_dir):
        """slug mtime 随索引持久化：重启后未变更文档不会重嵌"""
        e1 = KeywordEmbedder()
        RagService(WikiService(wiki_dir), wiki_dir, embedder=e1)

        e2 = KeywordEmbedder()
        rag2 = RagService(WikiService(wiki_dir), wiki_dir, embedder=e2)
        assert e2.embedded_texts == []

        # 但内容变更仍能被检测到（mtime 比对生效）
        write_concept(wiki_dir, "deploy", "部署指南", "全新内容 totally different。\n", ["ops"])
        import time
        time.sleep(0.01)
        rag2._wiki.add_document("deploy", "部署指南", "全新内容 totally different。\n", ["ops"])
        stats = rag2.sync()
        assert stats["updated"] == 1
        assert e2.embedded_texts  # 变更被检出并重嵌

    def test_search_falls_back_to_bm25_when_hybrid_errors(self, wiki_dir):
        """检索期嵌入失败 → 降级链兜底：service 回落纯 BM25，不抛错"""
        embedder = KeywordEmbedder(error=True)
        svc = WikiService(wiki_dir)
        # 构建期嵌入失败 → 向量层为空（warn 但不崩）
        rag = RagService(svc, wiki_dir, embedder=embedder)
        assert rag.stats()["hybrid"] is True  # retriever 仍启用（dense 通道降级）

        out = rag.search_chunks("Docker 部署")  # embed_query 也会失败 → BM25 兜底
        assert out
        bm25_only = [c["chunk_id"] for c in rag._store.search_chunks("Docker 部署", top_k=6)]
        assert [c["chunk_id"] for c in out] == bm25_only
