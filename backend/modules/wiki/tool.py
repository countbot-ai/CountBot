"""Wiki Tool - Agent工具接口"""

import json
import os
import re
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from loguru import logger

from backend.modules.tools.base import Tool
from backend.modules.tools._failure import format_failure, single_line
from backend.modules.tools.execution import ErrorCategory, RetrySafety, SideEffectState, ToolResult
from backend.modules.tools._path_resolver import resolve_path
from .service import WikiService


def _rag_chunks_enabled() -> bool:
    """M1 分块检索回滚开关：COUNTBOT_RAG_CHUNKS=1 启用，缺省关闭（零行为变化）"""
    return os.environ.get("COUNTBOT_RAG_CHUNKS", "").lower() in ("1", "true", "yes", "on")


def _rerank_enabled() -> bool:
    """Phase 2 精排开关：COUNTBOT_RAG_RERANK=1 启用，缺省关闭（零行为变化）"""
    return os.environ.get("COUNTBOT_RAG_RERANK", "").lower() in ("1", "true", "yes", "on")


class _BoundedCache:
    """查询结果 LRU（implementation-plan §5 Phase 2 任务 2.5）。

    grader/rerank 结果按 (query, chunk_ids) 缓存——生产实践：查询重复度
    比想象高。get 用哨兵区分"未命中"与"缓存了 falsy 值"。
    """

    _MISS = object()

    def __init__(self, capacity: int = 256):
        self._d: "OrderedDict[tuple, object]" = OrderedDict()
        self._cap = capacity

    def get(self, key: tuple):
        if key not in self._d:
            return self._MISS
        self._d.move_to_end(key)
        return self._d[key]

    def put(self, key: tuple, value) -> None:
        self._d[key] = value
        self._d.move_to_end(key)
        if len(self._d) > self._cap:
            self._d.popitem(last=False)


class WikiTool(Tool):
    """Wiki 知识库工具

    支持的操作:
    - search: 搜索 Wiki 条目（BM25 全文检索）
    - ask: 基于知识库内容回答问题
    - get: 获取特定条目内容
    - list: 列出所有条目
    - stats: 获取统计信息
    - create: 创建新条目
    - update: 更新现有条目
    - delete: 删除条目
    - sync: 同步索引（检测文件变更）
    """

    def __init__(self, wiki_dir: Optional[Path] = None):
        # 显式目录（如独立知识库 / 测试临时目录）不跟随工作空间热切换；
        # 默认 None = 跟随当前工作空间下的 wiki/ 目录（运行期热切换自动跟随）。
        self._explicit_wiki_dir = wiki_dir
        self._wiki_dir = self._resolve_wiki_dir(wiki_dir)
        self._build_service()

    def _resolve_wiki_dir(self, wiki_dir: Optional[Path]) -> Path:
        if wiki_dir is not None:
            return Path(wiki_dir).expanduser().resolve()
        return resolve_path("wiki")

    def _build_service(self) -> None:
        """按当前 _wiki_dir 重建服务（目录切换后重建索引载体）。"""
        self._service = WikiService(self._wiki_dir)
        self._rag = None
        if _rag_chunks_enabled():
            try:
                from backend.modules.rag.service import RagService
                self._rag = RagService(self._service, self._wiki_dir)
                logger.info("RAG chunk-level retrieval enabled (COUNTBOT_RAG_CHUNKS=1)")
            except Exception as e:
                logger.warning(f"RAG chunk service unavailable, falling back to doc-level: {e}")
                self._rag = None

        # Phase 2 精排层（COUNTBOT_RAG_RERANK=1，缺省关闭 = M1/CRAG 行为不变）
        self._reranker = None
        if self._rag is not None and _rerank_enabled():
            from backend.modules.rag.reranker import build_reranker
            try:
                self._reranker = build_reranker()
                if self._reranker:
                    logger.info("RAG rerank enabled (COUNTBOT_RAG_RERANK=1)")
            except Exception as e:
                logger.warning(f"Reranker unavailable, keeping retrieval order: {e}")
                self._reranker = None

        self._grade_cache = _BoundedCache()
        self._rerank_cache = _BoundedCache()

    def _sync_wiki_dir(self) -> None:
        """工作空间热切换后，默认 wiki 目录跟随新工作空间（显式目录除外）。"""
        if self._explicit_wiki_dir is not None:
            return
        current = resolve_path("wiki")
        if current != self._wiki_dir:
            logger.info(
                f"Wiki directory follows workspace switch: {self._wiki_dir} -> {current}"
            )
            self._wiki_dir = current
            self._build_service()

    @property
    def name(self) -> str:
        return "wiki"

    @property
    def description(self) -> str:
        return (
            "Wiki knowledge base with BM25 search. "
            "search returns title+tags+summary (usually sufficient). "
            "For multiple entries, use batch_get with slugs array (NOT multiple get calls). "
            "Other actions: ask, get, list, stats, create, update, delete, sync."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Action: search (with summary), get (full content), batch_get, ask, list, stats, create, update, delete, sync",
                    "enum": ["search", "ask", "get", "batch_get", "list", "stats", "create", "update", "delete", "sync"],
                },
                "query": {
                    "type": "string",
                    "description": "Search query or question (for search/ask actions)",
                },
                "slug": {
                    "type": "string",
                    "description": "Wiki entry slug (unique identifier)",
                },
                "slugs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of wiki entry slugs for batch_get (use this instead of multiple get calls)",
                },
                "title": {
                    "type": "string",
                    "description": "Entry title (for create/update)",
                },
                "content": {
                    "type": "string",
                    "description": "Entry content in Markdown format (for create/update)",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of tags (for create/update)",
                },
                "tag": {
                    "type": "string",
                    "description": "Filter by tag (for list action)",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Maximum number of search results",
                    "default": 10,
                },
            },
            "required": ["action"],
        }

    async def execute(
        self,
        action: str,
        query: Optional[str] = None,
        slug: Optional[str] = None,
        slugs: Optional[list] = None,
        title: Optional[str] = None,
        content: Optional[str] = None,
        tags: Optional[list] = None,
        tag: Optional[str] = None,
        top_k: int = 10,
        **kwargs,
    ) -> str:
        """执行 Wiki 操作"""
        try:
            self._sync_wiki_dir()
            if action == "search":
                return self._handle_search(query, top_k)
            elif action == "ask":
                return await self._handle_ask(query)
            elif action == "get":
                return self._handle_get(slug)
            elif action == "batch_get":
                return self._handle_batch_get(slugs)
            elif action == "list":
                return self._handle_list(tag)
            elif action == "stats":
                return self._handle_stats()
            elif action == "create":
                return self._handle_create(title, content, tags)
            elif action == "update":
                return self._handle_update(slug, title, content, tags)
            elif action == "delete":
                return self._handle_delete(slug)
            elif action == "sync":
                return self._handle_sync()
            else:
                return f"Unknown action: {action}. Available: search, ask, get, batch_get, list, stats, create, update, delete, sync"
        except Exception as e:
            detail = f"Wiki {action} failed: {e}"
            logger.error(detail)
            return format_failure(
                kind="execution_error",
                summary=f"Wiki {action} failed: {single_line(e)}",
                next="check the wiki entry and arguments, then retry",
                detail=detail,
            )

    async def execute_outcome(
        self,
        action: str,
        query: Optional[str] = None,
        slug: Optional[str] = None,
        slugs: Optional[list] = None,
        title: Optional[str] = None,
        content: Optional[str] = None,
        tags: Optional[list] = None,
        tag: Optional[str] = None,
        top_k: int = 10,
        **kwargs,
    ) -> ToolResult:
        try:
            self._sync_wiki_dir()
        except Exception as exc:
            return self._wiki_failure(
                ErrorCategory.EXECUTION,
                f"Wiki workspace synchronization failed: {single_line(exc)}",
                RetrySafety.SAFE,
            )
        read_actions = {"search", "get", "list", "stats", "ask"}
        if action in read_actions:
            return await self._read_outcome(action, query, slug, tag, top_k)
        if action == "batch_get":
            if not slugs:
                return self._wiki_failure(ErrorCategory.VALIDATION, "Error: batch_get action requires 'slugs' parameter", RetrySafety.SAFE)
            articles = self._service.batch_get_documents(slugs)
            if not any(articles):
                return self._wiki_failure(ErrorCategory.VALIDATION, "No wiki entries found for the provided slugs", RetrySafety.SAFE)
            return self._wiki_success(self._handle_batch_get(slugs), RetrySafety.SAFE)
        if action == "create":
            return self._create_outcome(title, content, tags)
        if action == "update":
            return self._update_outcome(slug, title, content, tags)
        if action == "delete":
            return self._delete_outcome(slug)
        if action == "sync":
            return self._sync_outcome()
        return self._wiki_failure(
            ErrorCategory.VALIDATION,
            f"Unknown action: {action}. Available: search, ask, get, batch_get, list, stats, create, update, delete, sync",
            RetrySafety.SAFE,
        )

    @staticmethod
    def _wiki_success(text: str, retry_safety: RetrySafety) -> ToolResult:
        return ToolResult.success(text, retry_safety=retry_safety, side_effect_state=SideEffectState.NOT_APPLICABLE if retry_safety is RetrySafety.SAFE else SideEffectState.COMMITTED)

    @staticmethod
    def _wiki_failure(category: ErrorCategory, text: str, retry_safety: RetrySafety, *, side_effect_state: SideEffectState = SideEffectState.NOT_APPLICABLE) -> ToolResult:
        return ToolResult.failure(category, text, retry_safety=retry_safety, side_effect_state=side_effect_state)

    async def _read_outcome(self, action: str, query: Optional[str], slug: Optional[str], tag: Optional[str], top_k: int) -> ToolResult:
        try:
            if action in {"search", "ask"} and not query:
                return self._wiki_failure(ErrorCategory.VALIDATION, f"Error: {action} action requires 'query' parameter", RetrySafety.SAFE)
            if action == "get":
                if not slug:
                    return self._wiki_failure(ErrorCategory.VALIDATION, "Error: get action requires 'slug' parameter", RetrySafety.SAFE)
                if not self._service.get_document(slug):
                    return self._wiki_failure(ErrorCategory.VALIDATION, f"Wiki entry not found: {slug}", RetrySafety.SAFE)
                return self._wiki_success(self._handle_get(slug), RetrySafety.SAFE)
            if action == "search":
                return self._wiki_success(self._handle_search(query, top_k), RetrySafety.SAFE)
            if action == "ask":
                return self._wiki_success(await self._handle_ask(query), RetrySafety.SAFE)
            if action == "list":
                return self._wiki_success(self._handle_list(tag), RetrySafety.SAFE)
            return self._wiki_success(self._handle_stats(), RetrySafety.SAFE)
        except Exception as exc:
            return self._wiki_failure(ErrorCategory.EXECUTION, f"Wiki {action} failed: {single_line(exc)}", RetrySafety.SAFE)

    def _create_outcome(self, title: Optional[str], content: Optional[str], tags: Optional[list]) -> ToolResult:
        if not title:
            return self._wiki_failure(ErrorCategory.VALIDATION, "Error: create action requires 'title' parameter", RetrySafety.UNSAFE, side_effect_state=SideEffectState.NOT_ATTEMPTED)
        if not content:
            return self._wiki_failure(ErrorCategory.VALIDATION, "Error: create action requires 'content' parameter", RetrySafety.UNSAFE, side_effect_state=SideEffectState.NOT_ATTEMPTED)
        safe_slug = re.sub(r"[\s_-]+", "-", re.sub(r"[^\w\s一-鿿-]", "", title.lower().strip()))[:100] or "untitled"
        md_file = self._service._concepts_dir / f"{safe_slug}.md"
        if md_file.exists():
            return self._wiki_failure(ErrorCategory.VALIDATION, f"Error: Wiki entry '{safe_slug}' already exists. Use 'update' action to modify it.", RetrySafety.UNSAFE, side_effect_state=SideEffectState.NOT_ATTEMPTED)
        effect_started = False
        try:
            import frontmatter
            from datetime import datetime
            post = frontmatter.Post(content)
            now = datetime.now().isoformat()
            post.metadata.update({"title": title, "tags": tags or [], "summary": content[:200].strip(), "created": now, "updated": now})
            effect_started = True
            md_file.write_text(frontmatter.dumps(post, encoding="utf-8"), encoding="utf-8")
            self._service.add_document(safe_slug, title, content, tags or [])
            if self._rag:
                self._rag.on_document_added(safe_slug)
            return ToolResult.success(f"✓ Created wiki entry: **{title}** (slug: {safe_slug})\nTags: {', '.join(tags or [])}", retry_safety=RetrySafety.UNSAFE, side_effect_state=SideEffectState.COMMITTED)
        except Exception as exc:
            if effect_started:
                return ToolResult.unknown_outcome(ErrorCategory.EXECUTION, f"Error: Failed to create wiki entry: {exc}", retry_safety=RetrySafety.UNSAFE)
            return self._wiki_failure(ErrorCategory.EXECUTION, f"Error: Failed to create wiki entry: {exc}", RetrySafety.UNSAFE, side_effect_state=SideEffectState.NOT_ATTEMPTED)

    def _update_outcome(self, slug: Optional[str], title: Optional[str], content: Optional[str], tags: Optional[list]) -> ToolResult:
        if not slug:
            return self._wiki_failure(ErrorCategory.VALIDATION, "Error: update action requires 'slug' parameter", RetrySafety.UNSAFE, side_effect_state=SideEffectState.NOT_ATTEMPTED)
        md_file = self._service._concepts_dir / f"{slug}.md"
        if not md_file.exists():
            return self._wiki_failure(ErrorCategory.VALIDATION, f"Error: Wiki entry '{slug}' not found. Use 'create' action to create it.", RetrySafety.UNSAFE, side_effect_state=SideEffectState.NOT_ATTEMPTED)
        effect_started = False
        try:
            import frontmatter
            from datetime import datetime
            post = frontmatter.load(str(md_file))
            fields = []
            if title:
                post.metadata["title"] = title; fields.append("title")
            if content is not None:
                post.content = content; fields.append("content")
            if tags is not None:
                post.metadata["tags"] = tags; fields.append("tags")
            post.metadata["updated"] = datetime.now().isoformat()
            effect_started = True
            md_file.write_text(frontmatter.dumps(post, encoding="utf-8"), encoding="utf-8")
            self._service.add_document(slug, post.metadata.get("title", slug), post.content, post.metadata.get("tags", []))
            if self._rag:
                self._rag.on_document_added(slug)
            return ToolResult.success(f"✓ Updated wiki entry: **{post.metadata.get('title', slug)}** (slug: {slug})\nUpdated fields: {', '.join(fields)}", retry_safety=RetrySafety.UNSAFE, side_effect_state=SideEffectState.COMMITTED)
        except Exception as exc:
            if effect_started:
                return ToolResult.unknown_outcome(ErrorCategory.EXECUTION, f"Error: Failed to update wiki entry: {exc}", retry_safety=RetrySafety.UNSAFE)
            return self._wiki_failure(ErrorCategory.EXECUTION, f"Error: Failed to update wiki entry: {exc}", RetrySafety.UNSAFE, side_effect_state=SideEffectState.NOT_ATTEMPTED)

    def _delete_outcome(self, slug: Optional[str]) -> ToolResult:
        if not slug:
            return self._wiki_failure(ErrorCategory.VALIDATION, "Error: delete action requires 'slug' parameter", RetrySafety.UNSAFE, side_effect_state=SideEffectState.NOT_ATTEMPTED)
        md_file = self._service._concepts_dir / f"{slug}.md"
        if not md_file.exists():
            return self._wiki_failure(ErrorCategory.VALIDATION, f"Error: Wiki entry '{slug}' not found", RetrySafety.UNSAFE, side_effect_state=SideEffectState.NOT_ATTEMPTED)
        effect_started = False
        try:
            import frontmatter
            title = frontmatter.load(str(md_file)).metadata.get("title", slug)
            effect_started = True
            md_file.unlink()
            self._service.remove_document(slug)
            if self._rag:
                self._rag.on_document_removed(slug)
            return ToolResult.success(f"✓ Deleted wiki entry: **{title}** (slug: {slug})", retry_safety=RetrySafety.UNSAFE, side_effect_state=SideEffectState.COMMITTED)
        except Exception as exc:
            if effect_started:
                return ToolResult.unknown_outcome(ErrorCategory.EXECUTION, f"Error: Failed to delete wiki entry: {exc}", retry_safety=RetrySafety.UNSAFE)
            return self._wiki_failure(ErrorCategory.EXECUTION, f"Error: Failed to delete wiki entry: {exc}", RetrySafety.UNSAFE, side_effect_state=SideEffectState.NOT_ATTEMPTED)

    def _sync_outcome(self) -> ToolResult:
        try:
            stats = self._service.force_sync()
            if self._rag:
                rag_stats = self._rag.sync()
                stats = {key: stats[key] + rag_stats[key] for key in ("added", "updated", "deleted")}
            return ToolResult.success(f"✓ Index synchronized:\n• Added: {stats['added']} new entries\n• Updated: {stats['updated']} modified entries\n• Deleted: {stats['deleted']} removed entries", retry_safety=RetrySafety.UNSAFE, side_effect_state=SideEffectState.COMMITTED)
        except Exception as exc:
            return ToolResult.unknown_outcome(ErrorCategory.EXECUTION, f"Error: Failed to sync index: {exc}", retry_safety=RetrySafety.UNSAFE)

    def _handle_search(self, query: Optional[str], top_k: int) -> str:
        """处理搜索请求（优化版：使用search_with_metadata减少文件读取）"""
        if not query:
            return "Error: search action requires 'query' parameter"

        if self._rag:
            return self._rag_search(query, top_k)

        # 使用优化的搜索方法，包含元数据和相关性过滤
        results = self._service.search_with_metadata(query, top_k=top_k, min_score_ratio=0.3)

        if not results:
            return f"No wiki entries found for: {query}"

        max_score = results[0]["score"]
        lines = [f"Found {len(results)} wiki entries for '{query}':\n"]

        for i, result in enumerate(results, 1):
            doc_id = result["slug"]
            title = result["title"]
            score = result["score"]
            tags = result["tags"]
            summary = result["summary"]

            # 质量标签
            if score >= max_score * 0.8:
                quality = " [高相关]"
            elif score >= max_score * 0.5:
                quality = " [相关]"
            else:
                quality = " [低相关]"

            lines.append(f"{i}. **{title}** (score: {score:.2f}){quality}")
            lines.append(f"   Slug: {doc_id}")
            if tags:
                lines.append(f"   Tags: {', '.join(tags)}")
            lines.append(f"   {summary}")
            lines.append("")

        # 死胡同修复：检索结果带可精确取用的 slug 标识，
        # 供 batch_get 等下游直接消费，无需重新猜测条目。
        slugs = ", ".join(result["slug"] for result in results)
        return "\n".join(lines) + f"\nSlugs: {slugs}"

    async def _handle_ask(self, question: Optional[str]) -> str:
        """处理问答请求"""
        if not question:
            return "Error: ask action requires 'query' parameter"

        if self._rag:
            return await self._rag_ask(question)

        results = self._service.search(question, top_k=3)

        if not results:
            return "Wiki 知识库为空或没有找到相关内容。"

        # 构建上下文
        context_parts = []
        for doc_id, score in results:
            doc = self._service.get_document(doc_id)
            if doc:
                context_parts.append(f"### {doc['title']}\n{doc['content']}")

        context = "\n\n".join(context_parts)

        # 尝试使用LLM回答
        try:
            from backend.app import get_shared_provider
            provider = get_shared_provider()

            if not provider:
                return self._format_search_results(results)

            prompt = f"""请根据以下 Wiki 知识库内容回答问题。

问题：{question}

---

{context}

---

如果知识库中没有相关内容，请如实告知。"""
            return await provider.chat_completion(prompt, max_tokens=2000, temperature=0.3)
        except Exception:
            return self._format_search_results(results)

    # ---------- M1: 块级检索路径（COUNTBOT_RAG_CHUNKS=1 时生效） ----------

    def _rag_search(self, query: str, top_k: int) -> str:
        """块级搜索：返回条目 + 具体节，带 [slug#section] 溯源标识"""
        chunks = self._rag.search_chunks(query, top_k=top_k)
        if not chunks:
            return f"No wiki entries found for: {query}"

        max_score = chunks[0]["score"]
        lines = [f"Found {len(chunks)} matching sections for '{query}':\n"]
        for i, c in enumerate(chunks, 1):
            if c["score"] >= max_score * 0.8:
                quality = " [高相关]"
            elif c["score"] >= max_score * 0.5:
                quality = " [相关]"
            else:
                quality = " [低相关]"
            lines.append(f"{i}. **{c['doc_title']}** › {c['section']} (score: {c['score']:.2f}){quality}")
            lines.append(f"   Source: {c['chunk_id']}")
            if c.get("tags"):
                lines.append(f"   Tags: {', '.join(c['tags'])}")
            summary = c["content"].strip()[:200]
            lines.append(f"   {summary}")
            lines.append("")
        return "\n".join(lines)

    async def _rag_ask(self, question: str) -> str:
        """块级问答（Phase 2 形态）：检索 top-50 → rerank 精排 top-6 → grader（all/none 拒答判定）→ 生成。

        - reranker 可用且 top-1 高置信时跳过 grader 直出生成（置信门控，
          降单题 LLM 调用；Phase 2 验收 2.2 → ≤1.5 次的实现手段）；
        - reranker 失败 → 回落检索排序（RRF/BM25）取 top-6，质量降级不中断；
        - grader 判 none → 改写问题重试一次 → 仍 none → 如实拒答；
        - 评估不可用（无 provider / 调用失败 / 输出不可解析）→ 全部注入
          直接生成（M1 行为，零破坏降级链）。
        """
        if self._reranker is not None:
            chunks, confident = await self._retrieve_and_rerank(question)
        else:
            chunks = self._rag.search_chunks(question, top_k=6)
            confident = False

        if not chunks:
            return "Wiki 知识库为空或没有找到相关内容。"

        if confident:
            # top-1 精排分数达置信阈值：跳过 grader，直接生成（省一次 LLM 调用）。
            # 阈值默认 1.01 = 禁用（校准证据见 reranker.RERANK_CONFIDENT_SCORE 注释）
            return await self._generate_from_chunks(question, chunks)

        grade = await self._grade_chunks(question, chunks)

        if grade == "none":
            # 检索结果全不相关：改写问题重试一次，仍不相关则如实拒答
            rewritten = await self._rewrite_query(question)
            if rewritten and rewritten != question:
                if self._reranker is not None:
                    chunks2, _ = await self._retrieve_and_rerank(rewritten)
                else:
                    chunks2 = self._rag.search_chunks(rewritten, top_k=6)
                if chunks2:
                    # 重试轮不走置信门控：首轮已判 none，矛盾信号下以 grader 为准
                    grade2 = await self._grade_chunks(rewritten, chunks2)
                    if grade2 == "all":
                        return await self._generate_from_chunks(rewritten, chunks2)
            return ("Wiki 知识库中没有找到与该问题相关的内容。"
                    "（已检索并逐条校验相关性，结果均与问题无关；"
                    "可以换个问法重试，或确认知识库中是否已有相关条目。）")

        return await self._generate_from_chunks(question, chunks)

    async def _retrieve_and_rerank(self, query: str) -> Tuple[List[dict], bool]:
        """检索 top-50 候选 → rerank 精排取 top-6。

        Returns:
            (top_chunks, top1_confident)。confident=True 表示 rerank top-1
            分数达到置信阈值（reranker.RERANK_CONFIDENT_SCORE），调用方可
            跳过 grader 直出。rerank 失败 → 回落检索排序前 6 个，
            confident=False（降级路径必走 grader 把关）。

        候选池取 min_score_ratio=0：相对阈值会让 top-50 常只剩个位数候选
        （L1 评测实测的"阈值行为"）；候选质量由 reranker 精排把关。
        max_per_doc=0：候选池不做单文档截断（#114 的截断面向最终注入的
        top-6，候选阶段的多样性由 reranker 精排决定）。
        """
        candidates = self._rag.search_chunks(query, top_k=50, min_score_ratio=0.0, max_per_doc=0)
        if not candidates:
            return [], False

        key = (query, tuple(c["chunk_id"] for c in candidates))
        cached = self._rerank_cache.get(key)
        if cached is not _BoundedCache._MISS:
            return cached

        try:
            from backend.modules.rag.reranker import RERANK_CONFIDENT_SCORE
            ranked = await self._reranker.rerank(query, candidates)
        except Exception as e:
            logger.warning(f"Rerank failed, falling back to retrieval order: {e}")
            return candidates[:6], False

        result = (ranked[:6],
                  bool(ranked and ranked[0].get("rerank_score", 0.0) >= RERANK_CONFIDENT_SCORE))
        self._rerank_cache.put(key, result)
        return result

    # ---------- 块级问答的评估与路由组件（仅 COUNTBOT_RAG_CHUNKS=1 路径使用） ----------

    @staticmethod
    def _get_provider():
        """获取共享 LLM provider；不可用时返回 None（各调用方自行回退）"""
        try:
            from backend.app import get_shared_provider
            return get_shared_provider()
        except Exception:
            return None

    async def _grade_chunks(self, question: str, chunks: List[dict]) -> Optional[str]:
        """LLM 拒答判定（Phase 2 收缩后：只判 all/none，块过滤职责已移交 reranker）。

        Returns:
            "all" | "none"；评估不可用时 None（调用方回退全量生成，零破坏降级）。
            纯分数阈值无法做拒答：实测负样本 top1 分数与正样本重叠率 7/10。
        """
        key = (question, tuple(c["chunk_id"] for c in chunks))
        cached = self._grade_cache.get(key)
        if cached is not _BoundedCache._MISS:
            return cached

        provider = self._get_provider()
        if provider is None:
            return None

        lines = [
            f"{i}. {c['doc_title']} › {c['section']}：{c['content'].strip()[:300]}"
            for i, c in enumerate(chunks, 1)
        ]
        prompt = (
            "你是知识库检索质量评估器。判断检索结果中是否包含回答问题所需的"
            "具体信息。\n\n"
            f"问题：{question}\n\n"
            "检索结果（编号. 文档 › 章节：内容摘录）：\n" + "\n".join(lines) + "\n\n"
            '只输出一行 JSON，不要输出其他内容：\n'
            '{"grade": "all|none"}\n'
            "- all：至少一条结果包含与问题直接相关的具体信息"
            "（事实/数字/命令/配置，或能支撑回答的内容；"
            "跨文档问题允许各结果各覆盖一部分）\n"
            "- none：所有结果只是话题相近、缺少回答所需的具体内容，"
            "或与问题完全无关。问具体数字/名称/命令而结果中给不出该值时，"
            "必须判 none——证据不足时宁可拒答，"
            "不要让话题相近的块蒙混过关"
        )
        try:
            resp = await provider.chat_completion(prompt, max_tokens=200, temperature=0.0)
            grade = self._parse_grade(resp)
            if grade is not None:
                # 失败（None）不缓存：瞬时故障不该被 LRU 固化
                self._grade_cache.put(key, grade)
            return grade
        except Exception as e:
            logger.warning(f"Chunk grading failed, falling back to plain generation: {e}")
            return None

    @staticmethod
    def _parse_grade(text: str) -> Optional[str]:
        """解析评估输出为 "all"|"none"；不可解析时返回 None。

        Phase 2 契约收缩：已废弃的 partial 输出按不可解析处理
        （调用方回退全量生成，块过滤职责归 reranker）。
        """
        if not text:
            return None
        m = re.search(r"\{[^{}]*\}", text, re.S)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except Exception:
            return None
        grade = str(data.get("grade", "")).strip().lower()
        return grade if grade in ("all", "none") else None

    async def _rewrite_query(self, question: str) -> Optional[str]:
        """全不相关时，让 LLM 把问题改写为更贴近知识库术语的检索词（一次机会）"""
        provider = self._get_provider()
        if provider is None:
            return None
        prompt = (
            "把下面的问题改写成更适合知识库关键词检索的问法"
            "（保留原意，尽量使用文档中可能出现的术语，不要回答问题本身），"
            "只输出改写后的问题：\n" + question
        )
        try:
            resp = await provider.chat_completion(prompt, max_tokens=100, temperature=0.0)
            text = (resp or "").strip().strip('"').strip("\u201c\u201d")
            return text or None
        except Exception as e:
            logger.warning(f"Query rewrite failed: {e}")
            return None

    async def _generate_from_chunks(self, question: str, chunks: List[dict]) -> str:
        """用给定块组装上下文并生成回答；无 provider 或失败时回退块级搜索结果"""
        provider = self._get_provider()
        if not provider:
            return self._rag_search(question, top_k=6)

        context_parts = []
        for c in chunks:
            context_parts.append(
                f"### {c['doc_title']} › {c['section']}\n(来源: {c['chunk_id']})\n{c['content']}"
            )
        context = "\n\n".join(context_parts)

        prompt = f"""请根据以下 Wiki 知识库内容回答问题。引用时注明来源 [slug#section]。

问题：{question}

---

{context}

---

如果知识库中没有相关内容，请如实告知。"""
        try:
            answer = await provider.chat_completion(prompt, max_tokens=2000, temperature=0.3)
            if not answer.strip():
                # 推理模型可能把 max_tokens 全部耗在思考阶段，content 为空：
                # 加大预算重试一次，仍为空则回退块级搜索结果（绝不返回空串）
                logger.warning("Empty generation content (reasoning exhausted "
                               "max_tokens?), retrying with larger budget")
                answer = await provider.chat_completion(prompt, max_tokens=4000, temperature=0.3)
            return answer if answer.strip() else self._rag_search(question, top_k=6)
        except Exception:
            return self._rag_search(question, top_k=6)

    def _handle_get(self, slug: Optional[str]) -> str:
        """处理获取请求"""
        if not slug:
            return "Error: get action requires 'slug' parameter"

        article = self._service.get_document(slug)
        if not article:
            return f"Wiki entry not found: {slug}"

        lines = [f"# {article['title']}\n"]
        if article.get("tags"):
            lines.append(f"**Tags:** {', '.join(article['tags'])}\n")
        if article.get("summary"):
            lines.append(f"**Summary:** {article['summary']}\n")
        if article.get("content"):
            lines.append(article["content"])

        return "\n".join(lines)

    def _handle_batch_get(self, slugs: Optional[list]) -> str:
        """处理批量获取请求"""
        if not slugs:
            return "Error: batch_get action requires 'slugs' parameter"

        articles = self._service.batch_get_documents(slugs)

        if not any(articles):
            return f"No wiki entries found for the provided slugs"

        lines = []
        for i, article in enumerate(articles):
            if not article:
                continue

            lines.append(f"# {article['title']}\n")
            if article.get("tags"):
                lines.append(f"**Tags:** {', '.join(article['tags'])}\n")
            if article.get("summary"):
                lines.append(f"**Summary:** {article['summary']}\n")
            if article.get("content"):
                lines.append(article["content"])

            # 添加分隔符（除了最后一个）
            if i < len(articles) - 1:
                lines.append("\n---\n")

        return "\n".join(lines)

    def _handle_list(self, tag: Optional[str]) -> str:
        """处理列表请求"""
        articles = self._service.list_documents(tag)

        if not articles:
            return f"No wiki entries found{' (tag: ' + tag + ')' if tag else ''}"

        lines = [f"Wiki entries ({len(articles)} total):\n"]
        for i, a in enumerate(articles, 1):
            lines.append(f"{i}. **{a['title']}**")
            lines.append(f"   Slug: {a['slug']}")
            if a.get("tags"):
                lines.append(f"   Tags: {', '.join(a['tags'])}")
            if a.get("summary"):
                lines.append(f"   {a['summary'][:100]}")
            lines.append("")

        return "\n".join(lines)

    def _handle_stats(self) -> str:
        """处理统计请求"""
        stats = self._service.get_stats()
        return (
            f"Wiki Statistics:\n"
            f"• Articles: {stats['article_count']}\n"
            f"• BM25 indexed: {stats['indexed_count']}\n"
            f"• Unique terms: {stats['unique_terms']}\n"
            f"• Average doc length: {stats['avg_doc_length']:.0f} tokens"
        )

    def _format_search_results(self, results: list) -> str:
        """格式化搜索结果为文本"""
        lines = []
        for doc_id, score in results:
            doc = self._service.get_document(doc_id)
            if doc:
                lines.append(f"**{doc['title']}** (score: {score:.2f})")
                lines.append(doc['content'][:300])
                lines.append("")
        return "\n".join(lines) or "No results found"

    def _handle_create(self, title: Optional[str], content: Optional[str], tags: Optional[list]) -> str:
        """处理创建请求"""
        if not title:
            return "Error: create action requires 'title' parameter"
        if not content:
            return "Error: create action requires 'content' parameter"

        import re
        from datetime import datetime
        import frontmatter

        # 生成 slug
        slug = title.lower().strip()
        slug = re.sub(r'[^\w\s一-鿿-]', '', slug)
        slug = re.sub(r'[\s_-]+', '-', slug)
        slug = slug[:100] or "untitled"

        # 检查是否已存在
        md_file = self._service._concepts_dir / f"{slug}.md"
        if md_file.exists():
            return f"Error: Wiki entry '{slug}' already exists. Use 'update' action to modify it."

        # 创建文件
        try:
            now = datetime.now().isoformat()
            post = frontmatter.Post(content)
            post.metadata["title"] = title
            post.metadata["tags"] = tags or []
            post.metadata["summary"] = content[:200].strip()
            post.metadata["created"] = now
            post.metadata["updated"] = now

            md_content = frontmatter.dumps(post, encoding="utf-8")
            md_file.write_text(md_content, encoding="utf-8")

            # 更新索引
            self._service.add_document(slug, title, content, tags or [])
            if self._rag:
                self._rag.on_document_added(slug)

            logger.info(f"Created wiki entry: {slug}")
            return f"✓ Created wiki entry: **{title}** (slug: {slug})\nTags: {', '.join(tags or [])}"
        except Exception as e:
            logger.error(f"Failed to create wiki entry: {e}")
            return f"Error: Failed to create wiki entry: {e}"

    def _handle_update(self, slug: Optional[str], title: Optional[str], content: Optional[str], tags: Optional[list]) -> str:
        """处理更新请求"""
        if not slug:
            return "Error: update action requires 'slug' parameter"

        md_file = self._service._concepts_dir / f"{slug}.md"
        if not md_file.exists():
            return f"Error: Wiki entry '{slug}' not found. Use 'create' action to create it."

        try:
            import frontmatter
            from datetime import datetime

            post = frontmatter.load(str(md_file))

            # 更新字段
            updated_fields = []
            if title:
                post.metadata["title"] = title
                updated_fields.append("title")
            if content is not None:
                post.content = content
                updated_fields.append("content")
            if tags is not None:
                post.metadata["tags"] = tags
                updated_fields.append("tags")

            post.metadata["updated"] = datetime.now().isoformat()

            # 保存文件
            md_content = frontmatter.dumps(post, encoding="utf-8")
            md_file.write_text(md_content, encoding="utf-8")

            # 更新索引
            self._service.add_document(
                slug,
                post.metadata.get("title", slug),
                post.content,
                post.metadata.get("tags", [])
            )
            if self._rag:
                self._rag.on_document_added(slug)

            logger.info(f"Updated wiki entry: {slug}")
            return f"✓ Updated wiki entry: **{post.metadata.get('title', slug)}** (slug: {slug})\nUpdated fields: {', '.join(updated_fields)}"
        except Exception as e:
            logger.error(f"Failed to update wiki entry: {e}")
            return f"Error: Failed to update wiki entry: {e}"

    def _handle_delete(self, slug: Optional[str]) -> str:
        """处理删除请求"""
        if not slug:
            return "Error: delete action requires 'slug' parameter"

        md_file = self._service._concepts_dir / f"{slug}.md"
        if not md_file.exists():
            return f"Error: Wiki entry '{slug}' not found"

        try:
            # 获取标题用于确认消息
            import frontmatter
            post = frontmatter.load(str(md_file))
            title = post.metadata.get("title", slug)

            # 删除文件
            md_file.unlink()

            # 更新索引
            self._service.remove_document(slug)
            if self._rag:
                self._rag.on_document_removed(slug)

            logger.info(f"Deleted wiki entry: {slug}")
            return f"✓ Deleted wiki entry: **{title}** (slug: {slug})"
        except Exception as e:
            logger.error(f"Failed to delete wiki entry: {e}")
            return f"Error: Failed to delete wiki entry: {e}"

    def _handle_sync(self) -> str:
        """处理同步请求"""
        try:
            stats = self._service.force_sync()
            if self._rag:
                rag_stats = self._rag.sync()
                stats = {
                    "added": stats["added"] + rag_stats["added"],
                    "updated": stats["updated"] + rag_stats["updated"],
                    "deleted": stats["deleted"] + rag_stats["deleted"],
                }
            return (
                f"✓ Index synchronized:\n"
                f"• Added: {stats['added']} new entries\n"
                f"• Updated: {stats['updated']} modified entries\n"
                f"• Deleted: {stats['deleted']} removed entries"
            )
        except Exception as e:
            logger.error(f"Failed to sync index: {e}")
            return f"Error: Failed to sync index: {e}"
