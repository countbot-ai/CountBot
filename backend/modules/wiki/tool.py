"""Wiki Tool - Agent工具接口"""

from pathlib import Path
from typing import Any, Dict, Optional
from loguru import logger

from backend.modules.tools.base import Tool
from .service import WikiService


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
        self._service = WikiService(wiki_dir or Path("workspace/wiki"))

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
            logger.error(f"Wiki {action} failed: {e}")
            return f"Wiki {action} failed: {e}"

    def _handle_search(self, query: Optional[str], top_k: int) -> str:
        """处理搜索请求（优化版：使用search_with_metadata减少文件读取）"""
        if not query:
            return "Error: search action requires 'query' parameter"

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

        return "\n".join(lines)

    async def _handle_ask(self, question: Optional[str]) -> str:
        """处理问答请求"""
        if not question:
            return "Error: ask action requires 'query' parameter"

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

            logger.info(f"Deleted wiki entry: {slug}")
            return f"✓ Deleted wiki entry: **{title}** (slug: {slug})"
        except Exception as e:
            logger.error(f"Failed to delete wiki entry: {e}")
            return f"Error: Failed to delete wiki entry: {e}"

    def _handle_sync(self) -> str:
        """处理同步请求"""
        try:
            stats = self._service.force_sync()
            return (
                f"✓ Index synchronized:\n"
                f"• Added: {stats['added']} new entries\n"
                f"• Updated: {stats['updated']} modified entries\n"
                f"• Deleted: {stats['deleted']} removed entries"
            )
        except Exception as e:
            logger.error(f"Failed to sync index: {e}")
            return f"Error: Failed to sync index: {e}"
