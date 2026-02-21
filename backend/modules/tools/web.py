"""Web 工具"""

import html
import json
import os
import re
from typing import Any
from urllib.parse import urlparse

import httpx
from loguru import logger

from backend.modules.tools.base import Tool

# 共享常量
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
MAX_REDIRECTS = 5  # 限制重定向次数以防止 DoS 攻击


def _strip_tags(text: str) -> str:
    """移除 HTML 标签并解码实体"""
    text = re.sub(r"<script[\s\S]*?</script>", "", text, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", "", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def _normalize(text: str) -> str:
    """规范化空白"""
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _validate_url(url: str) -> tuple[bool, str]:
    """
    验证 URL：必须是 http(s) 且有有效域名
    
    Returns:
        tuple[bool, str]: (是否有效, 错误消息)
    """
    try:
        p = urlparse(url)
        if p.scheme not in ("http", "https"):
            return False, f"Only http/https allowed, got '{p.scheme or 'none'}'"
        if not p.netloc:
            return False, "Missing domain"
        return True, ""
    except Exception as e:
        return False, str(e)


class WebSearchTool(Tool):
    """Web 搜索工具 - 使用 Brave Search API 进行网络搜索"""

    def __init__(self, api_key: str | None = None, max_results: int = 5):
        """
        初始化 Web 搜索工具
        
        Args:
            api_key: Brave Search API 密钥（可选，也可从环境变量获取）
            max_results: 默认返回结果数量
        """
        self.api_key = api_key or os.environ.get("BRAVE_API_KEY", "")
        self.max_results = max_results
        logger.debug("WebSearchTool initialized")

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return "Search the web using Brave Search API. Returns titles, URLs, and snippets."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query",
                },
                "count": {
                    "type": "integer",
                    "description": "Number of results (1-10)",
                    "minimum": 1,
                    "maximum": 10,
                },
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs: Any) -> str:
        """
        执行 Web 搜索
        
        Args:
            query: 搜索查询
            count: 返回结果数量
            
        Returns:
            str: 格式化的搜索结果或错误信息
        """
        query = kwargs.get("query", "")
        count = kwargs.get("count")
        
        if not query:
            return "Error: Query parameter is required"
        
        if not self.api_key:
            return "Error: BRAVE_API_KEY not configured"
        
        try:
            n = min(max(count or self.max_results, 1), 10)
            logger.info(f"Searching web: {query} (count: {n})")
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    params={"q": query, "count": n},
                    headers={
                        "Accept": "application/json",
                        "X-Subscription-Token": self.api_key,
                    },
                    timeout=10.0,
                )
                response.raise_for_status()
            
            results = response.json().get("web", {}).get("results", [])
            if not results:
                return f"No results for: {query}"
            
            lines = [f"Results for: {query}\n"]
            for i, item in enumerate(results[:n], 1):
                lines.append(f"{i}. {item.get('title', '')}\n   {item.get('url', '')}")
                if desc := item.get("description"):
                    lines.append(f"   {desc}")
            
            result = "\n".join(lines)
            logger.info(f"Web search completed: {len(results)} results")
            return result
            
        except Exception as e:
            logger.error(f"Web search error: {e}")
            return f"Error: {e}"


class WebFetchTool(Tool):
    """Web 内容获取工具

    从指定 URL 获取网页内容，优先使用 trafilatura，
    不可用时回退到 Readability。
    """

    def __init__(self, max_chars: int = 50000):
        """
        初始化 Web 获取工具
        
        Args:
            max_chars: 最大内容长度（字符）
        """
        self.max_chars = max_chars
        
        # 检查 trafilatura 是否可用
        try:
            import trafilatura
            self.use_trafilatura = True
            logger.debug(f"WebFetchTool initialized with trafilatura (max_chars: {max_chars})")
        except ImportError:
            self.use_trafilatura = False
            logger.debug(f"WebFetchTool initialized with readability (max_chars: {max_chars})")

    @property
    def name(self) -> str:
        return "web_fetch"

    @property
    def description(self) -> str:
        return "Fetch URL and extract readable content. Supports batch fetching multiple URLs. Use extractMode='markdown' to preserve links and structure, or 'text' (default) for plain text."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to fetch (single URL)",
                },
                "urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Multiple URLs to fetch (batch mode)",
                },
                "extractMode": {
                    "type": "string",
                    "enum": ["markdown", "text"],
                    "description": "Content extraction mode: 'text' (default, plain text) or 'markdown' (preserves links and structure)",
                },
                "maxChars": {
                    "type": "integer",
                    "minimum": 100,
                    "description": "Maximum characters to return per page",
                },
            },
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> str:
        """
        执行 Web 内容获取
        
        Args:
            url: 要获取的 URL（单个）
            urls: 要获取的 URL 列表（批量）
            extractMode: 提取模式（markdown 或 text）
            maxChars: 最大字符数
            
        Returns:
            str: JSON 格式的结果或错误信息
        """
        url = kwargs.get("url")
        urls = kwargs.get("urls")
        
        # 批量模式
        if urls:
            if not isinstance(urls, list):
                return json.dumps({"error": "urls must be a list"})
            
            results = []
            for u in urls:
                result = await self._fetch_single_url(u, kwargs)
                results.append(result)
            
            return json.dumps({"batch": True, "count": len(results), "results": results})
        
        # 单个 URL 模式
        if not url:
            return json.dumps({"error": "Either 'url' or 'urls' parameter is required"})
        
        result = await self._fetch_single_url(url, kwargs)
        return json.dumps(result)
    
    async def _fetch_single_url(self, url: str, kwargs: dict) -> dict:
        """
        获取单个 URL 的内容
        
        Args:
            url: URL
            kwargs: 参数字典
            
        Returns:
            dict: 结果字典
        """
        extract_mode = kwargs.get("extractMode", "text")
        max_chars = kwargs.get("maxChars", self.max_chars)
        
        # 验证 URL
        is_valid, error_msg = _validate_url(url)
        if not is_valid:
            return {"error": f"URL validation failed: {error_msg}", "url": url}
        
        try:
            logger.info(f"Fetching URL: {url}")
            
            async with httpx.AsyncClient(
                follow_redirects=True,
                max_redirects=MAX_REDIRECTS,
                timeout=30.0,
            ) as client:
                response = await client.get(url, headers={"User-Agent": USER_AGENT})
                response.raise_for_status()
            
            ctype = response.headers.get("content-type", "")
            
            # JSON 响应
            if "application/json" in ctype:
                text = json.dumps(response.json(), indent=2)
                title = ""
                extractor = "json"
            # HTML 响应
            elif "text/html" in ctype or response.text[:256].lower().startswith(
                ("<!doctype", "<html")
            ):
                if self.use_trafilatura:
                    # 使用 trafilatura（轻量级）
                    text, title, extractor = self._extract_with_trafilatura(response.text, extract_mode)
                else:
                    # 回退到 readability
                    text, title, extractor = self._extract_with_readability(response.text, extract_mode)
            else:
                text = response.text
                title = ""
                extractor = "raw"
            
            # 截断
            truncated = len(text) > max_chars
            if truncated:
                text = text[:max_chars]
            
            result = {
                "url": url,
                "finalUrl": str(response.url),
                "status": response.status_code,
                "title": title,
                "extractor": extractor,
                "truncated": truncated,
                "length": len(text),
                "text": text,
            }
            
            # 如果提取的内容太少，可能是 JavaScript 渲染的页面
            if len(text) < 500 and "text/html" in ctype:
                result["warning"] = "Content is very short. This page may require JavaScript rendering."
            
            logger.info(f"Fetched URL: {url} ({len(text)} characters, extractor: {extractor})")
            return result
            
        except Exception as e:
            logger.error(f"Web fetch error: {e}")
            return {"error": str(e), "url": url}
    
    def _extract_with_trafilatura(self, html: str, extract_mode: str) -> tuple[str, str, str]:
        """
        使用 trafilatura 提取内容
        
        Args:
            html: HTML 内容
            extract_mode: 提取模式
            
        Returns:
            tuple: (text, title, extractor_name)
        """
        try:
            import trafilatura
            
            if extract_mode == "markdown":
                # 直接提取为 markdown 格式
                text = trafilatura.extract(
                    html,
                    output_format='markdown',
                    include_comments=False,
                    include_tables=True,
                    include_links=True
                )
                
                # 如果提取失败，回退到 readability
                if not text:
                    logger.warning("Trafilatura markdown extraction returned empty, falling back to readability")
                    return self._extract_with_readability(html, extract_mode)
                
                # 尝试提取标题
                title_extracted = trafilatura.extract(
                    html,
                    output_format='json',
                    include_comments=False
                )
                title = ""
                if title_extracted:
                    try:
                        data = json.loads(title_extracted)
                        title = data.get('title', '')
                    except:
                        pass
                
                return text, title, "trafilatura"
            else:
                # 提取纯文本
                text = trafilatura.extract(
                    html,
                    output_format='txt',
                    include_comments=False,
                    include_tables=True
                )
                
                # 如果提取失败，回退到 readability
                if not text:
                    logger.warning("Trafilatura text extraction returned empty, falling back to readability")
                    return self._extract_with_readability(html, extract_mode)
                
                # 尝试提取标题
                title_extracted = trafilatura.extract(
                    html,
                    output_format='json',
                    include_comments=False
                )
                title = ""
                if title_extracted:
                    try:
                        data = json.loads(title_extracted)
                        title = data.get('title', '')
                    except:
                        pass
                
                return text, title, "trafilatura"
                
        except Exception as e:
            logger.warning(f"Trafilatura extraction failed: {e}, falling back to readability")
            return self._extract_with_readability(html, extract_mode)
    
    def _extract_with_readability(self, html: str, extract_mode: str) -> tuple[str, str, str]:
        """
        使用 readability 提取内容（回退方案）
        
        Args:
            html: HTML 内容
            extract_mode: 提取模式
            
        Returns:
            tuple: (text, title, extractor_name)
        """
        try:
            from readability import Document
            
            doc = Document(html)
            title = doc.title()
            
            if extract_mode == "markdown":
                content = self._to_markdown(doc.summary())
            else:
                content = _strip_tags(doc.summary())
            
            text = f"# {title}\n\n{content}" if title else content
            return text, title, "readability"
            
        except ImportError:
            logger.warning("Readability not available, using strip_tags")
            return _strip_tags(html), "", "strip_tags"
        except Exception as e:
            logger.warning(f"Readability extraction failed: {e}, falling back to strip_tags")
            return _strip_tags(html), "", "strip_tags"

    def _to_markdown(self, html_content: str) -> str:
        """
        将 HTML 转换为 Markdown
        
        Args:
            html_content: HTML 内容
            
        Returns:
            str: Markdown 格式的文本
        """
        # 转换链接
        text = re.sub(
            r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</a>',
            lambda m: f"[{_strip_tags(m[2])}]({m[1]})",
            html_content,
            flags=re.I,
        )
        # 转换标题
        text = re.sub(
            r"<h([1-6])[^>]*>([\s\S]*?)</h\1>",
            lambda m: f'\n{"#" * int(m[1])} {_strip_tags(m[2])}\n',
            text,
            flags=re.I,
        )
        # 转换列表
        text = re.sub(
            r"<li[^>]*>([\s\S]*?)</li>",
            lambda m: f"\n- {_strip_tags(m[1])}",
            text,
            flags=re.I,
        )
        # 转换段落
        text = re.sub(r"</(p|div|section|article)>", "\n\n", text, flags=re.I)
        text = re.sub(r"<(br|hr)\s*/?>", "\n", text, flags=re.I)
        
        return _normalize(_strip_tags(text))
