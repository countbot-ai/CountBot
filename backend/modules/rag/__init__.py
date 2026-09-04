"""RAG 增强模块

M1（分块 + BM25 分块级召回）：
- chunker.py: HeadingChunker，按 Markdown 标题切块
- stores/bm25_store.py: 分块级 BM25 索引（复用 wiki 的 BM25Index）
- service.py: RagService，挂在 WikiService 之上，增量同步

回滚开关：环境变量 COUNTBOT_RAG_CHUNKS=1 启用；缺省关闭（零行为变化）。
"""

from .chunker import Chunk, HeadingChunker  # noqa: F401
