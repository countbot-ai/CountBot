"""分块级 BM25 索引 - 复用 wiki 的 BM25Index

设计：每个 Chunk 作为 BM25Index 的一个"文档"（doc_id = chunk_id，
title = "文档标题 · 节路径"，content = 块正文，tags = 文档标签），
从而完整复用现有实现：jieba 分词、标题 ×3 / 标签 ×2 加权、倒排索引、
IDF、持久化。零算法重写。

slug -> chunk_id 的映射由 _slug_chunks 维护，支持按文档增删。
"""

import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from backend.modules.rag.chunker import Chunk, HeadingChunker
from backend.modules.wiki.index import BM25Index


class ChunkedBM25Index:
    """以块为检索单元的 BM25 索引"""

    def __init__(self, chunker: Optional[HeadingChunker] = None):
        self._bm25 = BM25Index()
        self._chunker = chunker or HeadingChunker()
        # chunk 元数据（slug/section/doc_title），BM25Index 里只存复合标题
        self._chunk_meta: Dict[str, dict] = {}
        # slug -> {mtime, chunk_ids}
        self._slug_registry: Dict[str, dict] = {}
        # chunk_id -> slug（快速反查）
        self._chunk_slug: Dict[str, str] = {}

    # ---------- 文档级 API（与 BM25Index 同形，便于上层替换） ----------

    def add_document(self, slug: str, title: str, content: str,
                     tags: List[str] = None, mtime: float = 0) -> int:
        """添加/替换文档（先移除旧块再切块），返回块数"""
        self._remove_slug(slug)
        chunks = self._chunker.chunk(slug, title, content, tags or [], mtime=mtime)
        for c in chunks:
            self._add_chunk(c)
        self._slug_registry[slug] = {"mtime": mtime, "chunk_ids": [c.chunk_id for c in chunks]}
        return len(chunks)

    def remove_document(self, slug: str) -> None:
        self._remove_slug(slug)

    def _remove_slug(self, slug: str) -> None:
        info = self._slug_registry.pop(slug, None)
        if not info:
            return
        for chunk_id in info["chunk_ids"]:
            self._bm25.remove_document(chunk_id)
            self._chunk_meta.pop(chunk_id, None)
            self._chunk_slug.pop(chunk_id, None)

    def _add_chunk(self, c: Chunk) -> None:
        self._bm25.add_document(c.chunk_id, c.index_title, c.content, c.tags, mtime=c.mtime)
        self._chunk_meta[c.chunk_id] = {
            "slug": c.slug,
            "doc_title": c.doc_title,
            "section": c.section,
            "heading_path": c.heading_path,
            "tags": c.tags,
        }
        self._chunk_slug[c.chunk_id] = c.slug

    def get_mtime(self, slug: str) -> float:
        return self._slug_registry.get(slug, {}).get("mtime", 0.0)

    def has_document(self, slug: str) -> bool:
        """该文档是否已在索引中（公共 API，避免上层触碰 _slug_registry）"""
        return slug in self._slug_registry

    def known_slugs(self) -> List[str]:
        """已索引文档的 slug 列表（公共 API）"""
        return list(self._slug_registry.keys())

    # ---------- 检索 ----------

    def search(self, query: str, top_k: int = 10, min_score_ratio: float = 0.3) -> List[Tuple[str, float]]:
        """搜索块，返回 [(chunk_id, score)]"""
        return self._bm25.search(query, top_k=top_k, min_score_ratio=min_score_ratio)

    def search_chunks(self, query: str, top_k: int = 10, min_score_ratio: float = 0.3) -> List[dict]:
        """搜索块，返回带元数据与正文的结果（注入用）"""
        results = self.search(query, top_k=top_k, min_score_ratio=min_score_ratio)
        out = []
        for chunk_id, score in results:
            meta = self._chunk_meta.get(chunk_id)
            if not meta:
                continue
            content = self._bm25.documents.get(chunk_id, {}).get("content", "")
            out.append({
                "chunk_id": chunk_id,
                "slug": meta["slug"],
                "doc_title": meta["doc_title"],
                "section": meta["section"],
                "score": score,
                "content": content,
            })
        return out

    def get_chunk(self, chunk_id: str) -> Optional[dict]:
        meta = self._chunk_meta.get(chunk_id)
        if not meta:
            return None
        doc = self._bm25.documents.get(chunk_id, {})
        return {**meta, "chunk_id": chunk_id, "content": doc.get("content", "")}

    # ---------- 统计 ----------

    def stats(self) -> dict:
        return {
            "total_docs": len(self._slug_registry),
            "total_chunks": len(self._chunk_meta),
            "unique_terms": len(self._bm25._inverted_index),
            "avg_chunk_length": self._bm25.avg_doc_length,
        }

    # ---------- 持久化 ----------

    def save_to_file(self, path: str) -> None:
        data = {
            "bm25": {
                "documents": self._bm25.documents,
                "doc_lengths": self._bm25.doc_lengths,
                "avg_doc_length": self._bm25.avg_doc_length,
                "total_docs": self._bm25.total_docs,
                "inverted_index": {
                    t: dict(df) for t, df in self._bm25._inverted_index.items()
                },
                "idf_cache": self._bm25._idf_cache,
            },
            "chunk_meta": self._chunk_meta,
            "chunk_slug": self._chunk_slug,
            "slug_registry": self._slug_registry,
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    def load_from_file(self, path: str) -> bool:
        p = Path(path)
        if not p.exists():
            return False
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            bm25_data = data["bm25"]
            self._bm25 = BM25Index()
            self._bm25.documents = bm25_data.get("documents", {})
            self._bm25.doc_lengths = bm25_data.get("doc_lengths", {})
            self._bm25.avg_doc_length = bm25_data.get("avg_doc_length", 0.0)
            self._bm25.total_docs = bm25_data.get("total_docs", 0)
            self._bm25._inverted_index = defaultdict(lambda: defaultdict(int))
            for t, df in bm25_data.get("inverted_index", {}).items():
                for cid, freq in df.items():
                    self._bm25._inverted_index[t][cid] = freq
            self._bm25._idf_cache = bm25_data.get("idf_cache", {})
            self._chunk_meta = data.get("chunk_meta", {})
            self._chunk_slug = data.get("chunk_slug", {})
            self._slug_registry = data.get("slug_registry", {})
            return True
        except Exception:
            return False
