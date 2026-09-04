"""RagService - WikiService 之上的分块检索服务

职责（M1）：
- 挂载在现有 WikiService 之上，按 mtime 增量同步分块索引；
- 对外提供 search_chunks（块级检索，注入用）；
- 持久化到 workspace/wiki/chunk_index.json，与现有 bm25_index.json 并存。

启用方式：环境变量 COUNTBOT_RAG_CHUNKS=1（见 wiki/tool.py）。
"""

from pathlib import Path
from typing import List, Optional

from loguru import logger


class RagService:
    """分块检索服务（包装 WikiService）"""

    INDEX_FILENAME = "chunk_index.json"

    def __init__(self, wiki_service, wiki_dir: Path):
        """依赖显式注入：wiki_service 仅用于读取文档，路径由调用方传入，
        不触碰 WikiService 私有属性。"""
        self._wiki = wiki_service
        self._concepts_dir = wiki_dir / "concepts"
        self._index_file = wiki_dir / self.INDEX_FILENAME

        from .stores import ChunkedBM25Index
        self._store = ChunkedBM25Index()

        if not self._store.load_from_file(str(self._index_file)):
            logger.info("Chunk index not found, building from wiki files")
            self.sync()

    # ---------- 同步 ----------

    def sync(self) -> dict:
        """增量同步：对照 concepts/*.md 的 mtime，增删改对应文档的块"""
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

        if any(stats.values()):
            self._store.save_to_file(str(self._index_file))
            logger.info(f"Chunk index synced: +{stats['added']} ~{stats['updated']} -{stats['deleted']}")
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
        return n

    def on_document_removed(self, slug: str) -> None:
        self._store.remove_document(slug)
        self._store.save_to_file(str(self._index_file))

    # ---------- 检索 ----------

    def search_chunks(self, query: str, top_k: int = 6, min_score_ratio: float = 0.3) -> List[dict]:
        """块级检索：返回 [{chunk_id, slug, doc_title, section, score, content}]"""
        return self._store.search_chunks(query, top_k=top_k, min_score_ratio=min_score_ratio)

    def stats(self) -> dict:
        return self._store.stats()
