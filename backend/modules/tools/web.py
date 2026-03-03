"""Web 工具 - 集成 Scrapling 反爬虫能力"""

import json
import os
import re
from contextlib import redirect_stdout
from typing import Any
from urllib.parse import urlparse

import httpx
from loguru import logger

from backend.modules.tools.base import Tool

# 尝试导入可选依赖
try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False
    logger.warning("BeautifulSoup4 not available, using regex-based text extraction")

try:
    import scrapling
    SCRAPLING_AVAILABLE = True
except ImportError:
    SCRAPLING_AVAILABLE = False

# 共享常量
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
MAX_REDIRECTS = 5


def _validate_url(url: str) -> tuple[bool, str]:
    """验证 URL：必须是 http(s) 且有有效域名"""
    try:
        p = urlparse(url)
        if p.scheme not in ("http", "https"):
            return False, f"Only http/https allowed, got '{p.scheme or 'none'}'"
        if not p.netloc:
            return False, "Missing domain"
        return True, ""
    except Exception as e:
        return False, str(e)


def _html_to_text_bs4(html: str) -> str:
    """使用 BeautifulSoup 提取纯文本（推荐方式）"""
    try:
        soup = BeautifulSoup(html, "lxml")
        # 移除 script 和 style 标签
        for script in soup(["script", "style", "noscript"]):
            script.extract()
        
        # 提取 body 内容
        body = soup.find("body")
        if body:
            text = body.get_text(separator="\n", strip=True)
        else:
            text = soup.get_text(separator="\n", strip=True)
        
        # 清理多余空行
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"BeautifulSoup extraction failed: {e}")
        return _html_to_text_regex(html)


def _html_to_text_regex(html: str) -> str:
    """使用正则表达式提取纯文本（回退方式，不依赖BS4）"""
    # 移除 script 和 style 标签及其内容
    text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<noscript[^>]*>.*?</noscript>', '', html, flags=re.DOTALL | re.IGNORECASE)
    
    # 移除注释
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
    
    # 移除所有 HTML 标签
    text = re.sub(r'<[^>]+>', '\n', text)
    
    # 解码 HTML 实体
    text = text.replace('&nbsp;', ' ')
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')
    text = text.replace('&amp;', '&')
    text = text.replace('&quot;', '"')
    text = text.replace('&#39;', "'")
    
    # 清理多余空白
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    return '\n'.join(lines)


def _html_to_text(html: str) -> str:
    """智能选择最佳的文本提取方式"""
    if BS4_AVAILABLE:
        return _html_to_text_bs4(html)
    else:
        return _html_to_text_regex(html)


async def _fetch_with_scrapling(url: str, mode: str = "basic") -> dict:
    """使用 Scrapling 获取网页内容
    
    Args:
        url: 目标 URL
        mode: 抓取模式 (basic/stealth/max-stealth)
        
    Returns:
        dict: 包含 html、status、final_url 的字典
    """
    try:
        # 导入 scrapling（延迟导入，避免启动时加载）
        with open(os.devnull, "w") as nullfd, redirect_stdout(nullfd):
            from scrapling.fetchers import AsyncFetcher, StealthyFetcher
        
        if mode == "basic":
            # 快速模式：使用 curl-cffi + 伪装 headers (1-2秒)
            response = await AsyncFetcher.get(url, stealthy_headers=True)
            return {
                "html": response.html_content,
                "status": response.status,
                "final_url": response.url,
                "mode": "basic"
            }
        
        elif mode == "stealth":
            # 隐身模式：使用 Playwright 无头浏览器 (3-8秒)
            response = await StealthyFetcher.async_fetch(
                url, 
                headless=True, 
                network_idle=True
            )
            return {
                "html": response.html_content,
                "status": response.status,
                "final_url": response.url,
                "mode": "stealth"
            }
        
        elif mode == "max-stealth":
            # 最强隐身模式：使用 Camoufox (10+秒)
            response = await StealthyFetcher.async_fetch(
                url,
                headless=True,
                block_webrtc=True,
                network_idle=True,
                disable_resources=False,
                block_images=False,
            )
            return {
                "html": response.html_content,
                "status": response.status,
                "final_url": response.url,
                "mode": "max-stealth"
            }
        
        else:
            raise ValueError(f"Unknown mode: {mode}")
            
    except ImportError:
        raise ImportError(
            "Scrapling not installed. Install with: pip install scrapling beautifulsoup4 lxml"
        )
    except Exception as e:
        logger.error(f"Scrapling fetch error: {e}")
        raise


class WebFetchTool(Tool):
    """Web 内容获取工具 - 集成 Scrapling 反爬虫能力
    
    支持三种抓取模式：
    - basic: 快速模式，使用 curl-cffi (1-2秒)
    - stealth: 隐身模式，使用 Playwright (3-8秒)
    - max-stealth: 最强模式，使用 Camoufox (10+秒)
    """

    def __init__(self, max_chars: int = 50000):
        self.max_chars = max_chars
        self.scrapling_available = SCRAPLING_AVAILABLE
        
        # 记录可用的功能
        features = []
        if SCRAPLING_AVAILABLE:
            features.append("Scrapling (anti-bot)")
        if BS4_AVAILABLE:
            features.append("BeautifulSoup4 (better extraction)")
        features.append("httpx (fallback)")
        
        logger.info(f"WebFetchTool initialized with: {', '.join(features)}")

    @property
    def name(self) -> str:
        return "web_fetch"

    @property
    def description(self) -> str:
        return "Fetch and extract web page content. Returns clean text by default (best for AI). Supports outputFormat: text/html/json. Supports mode: basic/stealth/max-stealth for anti-bot protection."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to fetch",
                },
                "mode": {
                    "type": "string",
                    "enum": ["basic", "stealth", "max-stealth"],
                    "description": "Anti-bot mode (default: basic)",
                },
                "outputFormat": {
                    "type": "string",
                    "enum": ["text", "html", "json"],
                    "description": "Output format (default: text)",
                },
                "maxChars": {
                    "type": "integer",
                    "minimum": 100,
                    "description": "Max characters to return",
                },
            },
            "required": ["url"],
        }

    async def execute(self, **kwargs: Any) -> str:
        url = kwargs.get("url")
        mode = kwargs.get("mode", "basic")
        output_format = kwargs.get("outputFormat", "text")
        max_chars = kwargs.get("maxChars", self.max_chars)
        
        if not url:
            return json.dumps({"error": "url parameter is required"})
        
        # 验证 URL
        is_valid, error_msg = _validate_url(url)
        if not is_valid:
            return json.dumps({"error": f"Invalid URL: {error_msg}", "url": url})
        
        try:
            logger.info(f"Fetching URL: {url} (mode: {mode}, format: {output_format})")
            
            # 使用 Scrapling 或回退到 httpx
            if self.scrapling_available and mode in ["basic", "stealth", "max-stealth"]:
                result = await self._fetch_with_scrapling(url, mode, max_chars, output_format)
            else:
                result = await self._fetch_with_httpx(url, max_chars, output_format)
            
            # 根据输出格式返回不同内容
            if output_format == "text":
                # 纯文本模式：直接返回文本（默认，最适合AI）
                logger.info(f"Fetched {url}: {len(result['text'])} chars (mode: {result.get('mode', 'httpx')}, format: text)")
                return result["text"]
            
            elif output_format == "html":
                # HTML模式：返回原始HTML
                logger.info(f"Fetched {url}: {len(result['html'])} chars (mode: {result.get('mode', 'httpx')}, format: html)")
                return result["html"]
            
            else:  # json
                # JSON模式：返回完整的结构化数据
                logger.info(f"Fetched {url}: {result['length']} chars (mode: {result.get('mode', 'httpx')}, format: json)")
                return json.dumps(result, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"Web fetch error for {url}: {e}")
            return json.dumps({"error": str(e), "url": url})
    
    async def _fetch_with_scrapling(self, url: str, mode: str, max_chars: int, output_format: str) -> dict:
        """使用 Scrapling 获取内容"""
        try:
            # 获取 HTML
            fetch_result = await _fetch_with_scrapling(url, mode)
            html = fetch_result["html"]
            
            # 提取纯文本
            text = _html_to_text(html)
            
            # 截断文本
            text_truncated = len(text) > max_chars
            if text_truncated:
                text = text[:max_chars]
            
            # 截断HTML（如果需要）
            html_truncated = len(html) > max_chars
            html_for_return = html[:max_chars] if html_truncated else html
            
            return {
                "url": url,
                "finalUrl": fetch_result["final_url"],
                "status": fetch_result["status"],
                "mode": fetch_result["mode"],
                "length": len(text),
                "truncated": text_truncated,
                "text": text,
                "html": html_for_return,
                "htmlTruncated": html_truncated,
            }
            
        except ImportError as e:
            logger.warning(f"Scrapling import error: {e}, falling back to httpx")
            return await self._fetch_with_httpx(url, max_chars, output_format)
        except Exception as e:
            raise Exception(f"Scrapling fetch failed: {e}")
    
    async def _fetch_with_httpx(self, url: str, max_chars: int, output_format: str) -> dict:
        """使用 httpx 获取内容（回退方案）"""
        async with httpx.AsyncClient(
            follow_redirects=True,
            max_redirects=MAX_REDIRECTS,
            timeout=30.0,
            verify=False,  # 禁用 SSL 验证以避免证书问题
        ) as client:
            response = await client.get(url, headers={"User-Agent": USER_AGENT})
            response.raise_for_status()
        
        ctype = response.headers.get("content-type", "")
        html = response.text
        
        # JSON 响应
        if "application/json" in ctype:
            text = json.dumps(response.json(), indent=2)
        # HTML 响应
        elif "text/html" in ctype or html[:256].lower().startswith(
            ("<!doctype", "<html")
        ):
            text = _html_to_text(html)
        else:
            text = html
        
        # 截断文本
        text_truncated = len(text) > max_chars
        if text_truncated:
            text = text[:max_chars]
        
        # 截断HTML（如果需要）
        html_truncated = len(html) > max_chars
        html_for_return = html[:max_chars] if html_truncated else html
        
        result = {
            "url": url,
            "finalUrl": str(response.url),
            "status": response.status_code,
            "mode": "httpx",
            "length": len(text),
            "truncated": text_truncated,
            "text": text,
            "html": html_for_return,
            "htmlTruncated": html_truncated,
        }
        
        # 如果内容太少，可能需要 JavaScript 渲染
        if len(text) < 500 and "text/html" in ctype:
            result["warning"] = "Content is very short. Try mode='stealth' for JavaScript-rendered pages."
        
        return result
