"""分层 Wiki：管理员只读层 + 用户可写层；同 slug 用户条目优先，写入只落用户目录。"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Set

from loguru import logger

from .service import WikiService


class LayeredWikiService:
    """只读层 + 可写层的组合视图。"""

    def __init__(self, writable: WikiService, readonly: Optional[WikiService] = None):
        self.writable = writable
        self.readonly = readonly

    # ------------------------------------------------------------------
    # 归属判断
    # ------------------------------------------------------------------

    def _readonly_slugs(self) -> Set[str]:
        if self.readonly is None:
            return set()
        return {article["slug"] for article in self.readonly.list_documents()}

    def is_readonly_slug(self, slug: str) -> bool:
        """该条目是否来自管理员只读层（用户不可改）。"""
        if self.readonly is None:
            return False
        if self.writable.get_document(slug) is not None:
            # 用户已创建同名条目时以用户条目为准（创建时已禁止同名，此处按既有条目处理）
            return False
        return self.readonly.get_document(slug) is not None

    def readonly_slugs(self) -> Set[str]:
        """只读层中被用户引用时需要拒绝写入的 slug 集合。"""
        own = {article["slug"] for article in self.writable.list_documents()}
        return self._readonly_slugs() - own

    # ------------------------------------------------------------------
    # 读：合并
    # ------------------------------------------------------------------

    def list_documents(self, tag: Optional[str] = None) -> List[dict]:
        merged: dict[str, dict] = {}
        if self.readonly is not None:
            for article in self.readonly.list_documents(tag):
                merged[article["slug"]] = article
        for article in self.writable.list_documents(tag):
            merged[article["slug"]] = article
        return sorted(merged.values(), key=lambda item: item.get("title") or item["slug"])

    def get_document(self, slug: str) -> Optional[dict]:
        doc = self.writable.get_document(slug)
        if doc is not None:
            return doc
        if self.readonly is not None:
            return self.readonly.get_document(slug)
        return None

    def batch_get_documents(self, slugs: List[str]) -> List[Optional[dict]]:
        return [self.get_document(slug) for slug in slugs]

    def search(self, query: str, top_k: int = 10) -> List[tuple]:
        merged: dict[str, float] = {}
        for doc_id, score in self.writable.search(query, top_k=top_k):
            merged[doc_id] = max(merged.get(doc_id, 0.0), score)
        if self.readonly is not None:
            for doc_id, score in self.readonly.search(query, top_k=top_k):
                merged[doc_id] = max(merged.get(doc_id, 0.0), score)
        ranked = sorted(merged.items(), key=lambda item: item[1], reverse=True)
        return ranked[:top_k]

    def search_with_metadata(self, query: str, top_k: int = 10, min_score_ratio: float = 0.3) -> List[dict]:
        merged: dict[str, dict] = {}
        if self.readonly is not None:
            for item in self.readonly.search_with_metadata(query, top_k=top_k, min_score_ratio=min_score_ratio):
                merged[item["slug"]] = item
        for item in self.writable.search_with_metadata(query, top_k=top_k, min_score_ratio=min_score_ratio):
            merged[item["slug"]] = item
        ranked = sorted(merged.values(), key=lambda item: item.get("score", 0), reverse=True)
        return ranked[:top_k]

    def search_with_snippets(self, query: str, top_k: int = 10) -> List[dict]:
        merged: dict[str, dict] = {}
        if self.readonly is not None:
            for item in self.readonly.search_with_snippets(query, top_k=top_k):
                merged[item["slug"]] = item
        for item in self.writable.search_with_snippets(query, top_k=top_k):
            merged[item["slug"]] = item
        ranked = sorted(merged.values(), key=lambda item: item.get("score", 0), reverse=True)
        return ranked[:top_k]

    def get_stats(self) -> dict:
        own = self.writable.get_stats()
        if self.readonly is None:
            return own
        shared = self.readonly.get_stats()
        readonly_only = len(self.readonly_slugs())
        return {
            "article_count": own["article_count"] + readonly_only,
            "indexed_count": own["indexed_count"] + readonly_only,
            "unique_terms": own["unique_terms"] + shared["unique_terms"],
            "avg_doc_length": own.get("avg_doc_length", 0),
        }

    def get_backlinks(self, slug: str) -> List[dict]:
        merged: dict[str, dict] = {}
        if self.readonly is not None:
            for item in self.readonly.get_backlinks(slug):
                merged[item["slug"]] = item
        for item in self.writable.get_backlinks(slug):
            merged[item["slug"]] = item
        return list(merged.values())

    # ------------------------------------------------------------------
    # 写：只落用户层
    # ------------------------------------------------------------------

    def force_sync(self) -> dict:
        stats = self.writable.force_sync()
        if self.readonly is not None:
            # 管理员层由管理员自己的请求维护，这里只同步用户层，避免并发写同一个索引文件
            logger.debug("Layered wiki sync: writable layer only")
        return stats

    def add_document(self, doc_id: str, title: str, content: str, tags: List[str] = None) -> None:
        self.writable.add_document(doc_id, title, content, tags)

    def remove_document(self, doc_id: str) -> None:
        self.writable.remove_document(doc_id)

    @property
    def concepts_dir(self) -> Path:
        """可写层的 concepts 目录（写文件必须落在这里）。"""
        return self.writable._concepts_dir  # noqa: SLF001 - 同模块内部约定
