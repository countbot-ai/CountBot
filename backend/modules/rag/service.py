"""RagService - WikiService 之上的分块检索服务

职责：
- M1：挂载在现有 WikiService 之上，按 mtime 增量同步分块 BM25 索引，
  对外提供 search_chunks（块级检索，注入用），持久化 chunk_index.json；
- M2（Phase 1 任务 4）：COUNTBOT_RAG_HYBRID=1 且嵌入端点已配置时，
  同一 sync 事务内对新增/变更块双写向量（vector_index.npz/.json），
  search_chunks 分派到 HybridRetriever（BM25 + Dense RRF 融合）。

降级链（§4 三层防御第③层）：任一环未配置或失败，逐级回落到
上一已验证形态——混合失败回落纯 BM25，纯 BM25 即 M1 现状。

同步/异步桥接说明：search_chunks 保持同步签名（tool 层零改动的前提），
嵌入调用经 _run_coro 在独立线程的事件循环中执行——可从任何上下文
（同步工具处理、async ask、事件循环内）安全调用。代价是查询路径上
调用线程阻塞一个嵌入 RTT（个人运行时可接受）；Phase 2 改造 _rag_ask
时顺势全链路异步化。

启用方式：COUNTBOT_RAG_CHUNKS=1（M1）+ COUNTBOT_RAG_HYBRID=1 与
COUNTBOT_RAG_EMBEDDING_*（M2，见 embeddings.py）。
"""

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List

from loguru import logger


def _hybrid_enabled() -> bool:
    """M2 混合检索开关（默认关 = 纯 BM25，与 M1 行为完全一致）"""
    return os.environ.get("COUNTBOT_RAG_HYBRID", "").lower() in ("1", "true", "yes", "on")


def _run_coro(coro):
    """在独立线程的事件循环中执行协程

    必须用线程而非 asyncio.run：调用方可能已在事件循环内（async ask 路径），
    asyncio.run 会抛 RuntimeError；线程内的独立循环不受影响。
    """
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def chunk_embedding_text(chunk: dict) -> str:
    """块的嵌入文本 = 「文档标题 › 节路径 + 块正文」

    与 BM25 的标题加权（title ×3）对齐，让 Dense 通道也吃到标题上下文。
    独立成函数：评测脚本（l1_eval.py 的 G2/G3 run）必须与生产用同一组装，
    否则向量空间不可比。
    """
    return f"{chunk['doc_title']} › {chunk.get('heading_path', chunk['section'])}\n{chunk['content']}"


class RagService:
    """分块检索服务（包装 WikiService）"""

    INDEX_FILENAME = "chunk_index.json"

    def __init__(self, wiki_service, wiki_dir: Path, embedder=None):
        """依赖显式注入：wiki_service 仅用于读取文档，路径由调用方传入，
        不触碰 WikiService 私有属性。embedder 可注入（测试用），
        缺省在混合开关开启时从环境变量构造。"""
        self._wiki = wiki_service
        self._concepts_dir = wiki_dir / "concepts"
        self._index_file = wiki_dir / self.INDEX_FILENAME

        from .stores import ChunkedBM25Index
        self._store = ChunkedBM25Index()

        self._embedder = None          # 先置空：首建 BM25 的 sync() 会读到
        self._vector_store = None
        self._retriever = None
        self._vector_file = None

        if not self._store.load_from_file(str(self._index_file)):
            logger.info("Chunk index not found, building from wiki files")
            self.sync()

        # ---- M2 混合检索（Phase 1 任务 4）----
        if embedder is not None:
            self._embedder = embedder
        elif _hybrid_enabled():
            from .embeddings import build_embedding_client
            self._embedder = build_embedding_client()

        if self._embedder is not None:
            self._init_vector_layer(wiki_dir)

    # ---------- M2 向量层 ----------

    def _init_vector_layer(self, wiki_dir: Path) -> None:
        from .retriever import HybridRetriever
        from .stores import VectorStore
        from .stores.vector_store import default_index_filename

        self._vector_file = wiki_dir / default_index_filename()
        self._vector_store = VectorStore()
        if not self._vector_store.load_from_file(str(self._vector_file)):
            logger.info("Vector index not found, embedding all chunks (first hybrid run)")

        stats = {"vectors_embedded": 0}
        self._sync_vectors_incremental(stats)  # 清漂移 + 补缺失（含首建全量）
        if stats["vectors_embedded"]:
            logger.info(f"Vector index built: {stats['vectors_embedded']} chunks embedded")

        self._retriever = HybridRetriever(self._store, self._vector_store, self._embedder)
        logger.info(f"Hybrid retrieval enabled "
                    f"({len(self._vector_store)} vectors, dim={self._vector_store.dim})")

    def _embed_slug(self, slug: str) -> int:
        """单文档双写：对该文档全部块计算向量并写入向量索引

        嵌入文本 = 「文档标题 › 节路径 + 块正文」——与 BM25 的标题加权
        （title ×3）对齐，让 Dense 通道也能吃到标题上下文。
        失败时跳过该文档（检索自动回落 BM25-only），不阻断同步。
        """
        chunk_ids = self._store.chunk_ids_of(slug)
        chunks = [c for c in (self._store.get_chunk(cid) for cid in chunk_ids) if c]
        if not chunks:
            return 0
        texts = [chunk_embedding_text(c) for c in chunks]
        try:
            vectors = _run_coro(self._embedder.embed_texts(texts))
        except Exception as e:
            logger.warning(f"Embedding failed for '{slug}' ({len(texts)} chunks), "
                           f"vector channel will miss it: {e}")
            return 0
        for chunk_id, vec in zip([c["chunk_id"] for c in chunks], vectors):
            self._vector_store.add(chunk_id, vec)
        # 记录该文档的嵌入时点（BM25 mtime）：chunk_id 在内容变更时可能
        # 复用（同 slug#section），仅凭 id 存在无法判定向量过期，mtime 才可靠
        self._vector_store.meta.setdefault("slug_mtimes", {})[slug] = self._store.get_mtime(slug)
        return len(vectors)

    def _sync_vectors_incremental(self, stats: dict | None = None) -> None:
        """向量索引与 BM25 对齐：清漂移（多余向量）+ 补缺失 + 内容过期重嵌"""
        if stats is None:
            stats = {}
        live = set(self._store.all_chunk_ids())
        stale = [cid for cid in self._vector_store.ids() if cid not in live]
        for cid in stale:
            self._vector_store.remove(cid)

        mtimes: dict = self._vector_store.meta.get("slug_mtimes", {})
        known = set(self._store.known_slugs())
        for slug in self._store.known_slugs():
            chunk_ids = self._store.chunk_ids_of(slug)
            missing = any(not self._vector_store.has(cid) for cid in chunk_ids)
            expired = self._store.get_mtime(slug) > mtimes.get(slug, 0.0)
            if missing or expired:
                # 重嵌前清掉该文档旧向量（块数缩减时旧 id 不会自动消失）
                for cid in chunk_ids:
                    self._vector_store.remove(cid)
                stats["vectors_embedded"] = stats.get("vectors_embedded", 0) + self._embed_slug(slug)

        for dead in [s for s in mtimes if s not in known]:
            mtimes.pop(dead)
        self._save_vector_index()

    def _save_vector_index(self) -> None:
        try:
            self._vector_store.save_to_file(str(self._vector_file))
        except Exception as e:
            logger.warning(f"Vector index save failed: {e}")

    # ---------- 同步 ----------

    def sync(self) -> dict:
        """增量同步：对照 concepts/*.md 的 mtime，增删改对应文档的块（双写向量）"""
        stats = {"added": 0, "updated": 0, "deleted": 0}

        current: dict = {}
        for md_file in self._concepts_dir.glob("*.md"):
            current[md_file.stem] = md_file.stat().st_mtime

        # 删除已不存在的文档
        for slug in self._store.known_slugs():
            if slug not in current:
                self._store.remove_document(slug)
                stats["deleted"] += 1

        for slug, mtime in current.items():
            if not self._store.has_document(slug):
                action = "added"
            elif mtime > self._store.get_mtime(slug):
                action = "updated"
            else:
                continue
            doc = self._wiki.get_document(slug)
            if not doc:
                continue
            self._store.add_document(slug, doc["title"], doc["content"], doc.get("tags", []), mtime=mtime)
            stats[action] += 1

        if stats["added"] or stats["updated"] or stats["deleted"]:
            self._store.save_to_file(str(self._index_file))
            logger.info(f"Chunk index synced: +{stats['added']} ~{stats['updated']} -{stats['deleted']}")
            # 同一 sync 事务内双写向量（§9：向量与 BM25 漂移 → 同步双写）
            if self._embedder is not None:
                self._sync_vectors_incremental()
        return stats

    # ---------- 文档变更钩子（tool 层 create/update/delete 后调用） ----------

    def on_document_added(self, slug: str) -> int:
        """单文档重建：只重新分块该文档（add_document 先删旧块再切块），
        避免一次全量 sync。返回该文档的块数。"""
        doc = self._wiki.get_document(slug)
        if not doc:
            return 0
        md_file = self._concepts_dir / f"{slug}.md"
        mtime = md_file.stat().st_mtime if md_file.exists() else 0.0
        n = self._store.add_document(
            slug, doc["title"], doc["content"], doc.get("tags", []), mtime=mtime
        )
        self._store.save_to_file(str(self._index_file))
        logger.debug(f"Chunk index rebuilt for '{slug}': {n} chunks")
        if self._embedder is not None:
            self._sync_vectors_incremental()
        return n

    def on_document_removed(self, slug: str) -> None:
        self._store.remove_document(slug)
        self._store.save_to_file(str(self._index_file))
        if self._embedder is not None:
            self._sync_vectors_incremental()

    # ---------- 检索 ----------

    def search_chunks(self, query: str, top_k: int = 6, min_score_ratio: float = 0.3,
                      max_per_doc: int = 1) -> List[dict]:
        """块级检索：返回 [{chunk_id, slug, doc_title, section, score, content}]

        混合启用时走 HybridRetriever（RRF 融合分，min_score_ratio / max_per_doc
        不参与——候选质量由双通道排序与下游 grader 把关）；否则纯 BM25
        （含 #114 的单文档截断语义，默认 max_per_doc=1 与其一致）。
        混合路径整体异常时回落纯 BM25（降级链）。
        """
        if self._retriever is not None:
            try:
                return _run_coro(self._retriever.search(query, top_k=top_k))
            except Exception as e:
                logger.warning(f"Hybrid retrieval failed, falling back to BM25: {e}")
        return self._store.search_chunks(query, top_k=top_k, min_score_ratio=min_score_ratio,
                                         max_per_doc=max_per_doc)

    def stats(self) -> dict:
        s = self._store.stats()
        if self._vector_store is not None:
            s["vector_chunks"] = len(self._vector_store)
            s["hybrid"] = self._retriever is not None
        return s
