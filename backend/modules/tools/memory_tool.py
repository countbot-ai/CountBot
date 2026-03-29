"""Memory Tool - 记忆管理工具

提供给 Agent 的记忆读写搜索能力:
- MemoryTool (memory): 统一工具，通过 action 参数区分 write / search / read
- MemoryWriteTool / MemorySearchTool / MemoryReadTool: 保留用于向后兼容
"""

from typing import Any, Dict, Optional
from loguru import logger
from backend.modules.tools.base import Tool
from backend.modules.agent.memory import MemoryStore


class MemoryWriteTool(Tool):
    """写入记忆"""

    def __init__(self, memory_store: MemoryStore):
        self._memory = memory_store
        self._channel: Optional[str] = None

    def set_channel(self, channel: Optional[str]) -> None:
        """设置当前渠道，用作记忆来源"""
        self._channel = channel

    @property
    def name(self) -> str:
        return "memory_write"

    @property
    def description(self) -> str:
        return "Write durable memory only."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Memory text.",
                },
            },
            "required": ["content"],
        }

    async def execute(self, content: str, **kwargs) -> str:
        try:
            source = self._channel or "web-chat"
            line_num = self._memory.append_entry(source=source, content=content)
            total = self._memory.get_line_count()
            return f"已写入记忆第 {line_num} 行（共 {total} 条）"
        except Exception as e:
            logger.error(f"Memory write failed: {e}")
            return f"写入记忆失败: {e}"


class MemorySearchTool(Tool):
    """搜索记忆"""

    def __init__(self, memory_store: MemoryStore):
        self._memory = memory_store

    @property
    def name(self) -> str:
        return "memory_search"

    @property
    def description(self) -> str:
        return "Search long-term memory."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "keywords": {
                    "type": "string",
                    "description": "Search keywords.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Max results.",
                    "default": 15,
                },
                "match_mode": {
                    "type": "string",
                    "description": "Match mode.",
                    "enum": ["or", "and"],
                    "default": "or",
                },
            },
            "required": ["keywords"],
        }

    async def execute(self, keywords: str, max_results: int = 15, match_mode: str = "or", **kwargs) -> str:
        try:
            keyword_list = keywords.strip().split()
            result = self._memory.search(keyword_list, max_results=max_results, match_mode=match_mode)
            stats = self._memory.get_stats()
            return f"记忆库共 {stats['total']} 条\n\n{result}"
        except Exception as e:
            logger.error(f"Memory search failed: {e}")
            return f"搜索记忆失败: {e}"


class MemoryReadTool(Tool):
    """读取记忆"""

    def __init__(self, memory_store: MemoryStore):
        self._memory = memory_store

    @property
    def name(self) -> str:
        return "memory_read"

    @property
    def description(self) -> str:
        return "Read memory lines or recent entries."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "start_line": {
                    "type": "integer",
                    "description": "1-based start line.",
                },
                "end_line": {
                    "type": "integer",
                    "description": "1-based end line.",
                },
                "recent_count": {
                    "type": "integer",
                    "description": "Recent entry count.",
                    "default": 10,
                },
            },
            "required": [],
        }

    async def execute(
        self,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        recent_count: int = 10,
        **kwargs,
    ) -> str:
        try:
            stats = self._memory.get_stats()
            header = f"记忆库共 {stats['total']} 条"
            if stats.get("date_range"):
                header += f"，时间范围: {stats['date_range']}"

            if start_line is not None:
                content = self._memory.read_lines(start_line, end_line)
            else:
                content = self._memory.get_recent(recent_count)

            return f"{header}\n\n{content}"
        except Exception as e:
            logger.error(f"Memory read failed: {e}")
            return f"读取记忆失败: {e}"


# ==============================================================================
# 统一记忆工具（推荐使用，减少工具数量节省 token）
# ==============================================================================


class MemoryTool(Tool):
    """统一记忆工具，通过 action 参数路由到 write / search / read 操作。

    将原来三个独立工具合并为一个，减少工具注册数量，节省每轮 LLM 调用的 token 消耗。
    """

    def __init__(self, memory_store: MemoryStore):
        self._memory = memory_store
        self._channel: Optional[str] = None

    def set_channel(self, channel: Optional[str]) -> None:
        """设置当前渠道，用作 write 操作的记忆来源"""
        self._channel = channel

    @property
    def name(self) -> str:
        return "memory"

    @property
    def description(self) -> str:
        return "Long-term memory: `write`, `search`, or `read`."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Memory action.",
                    "enum": ["write", "search", "read"],
                },
                "content": {
                    "type": "string",
                    "description": "Memory text.",
                },
                "keywords": {
                    "type": "string",
                    "description": "Search keywords.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Max results.",
                    "default": 15,
                },
                "match_mode": {
                    "type": "string",
                    "description": "Match mode.",
                    "enum": ["or", "and"],
                    "default": "or",
                },
                "start_line": {
                    "type": "integer",
                    "description": "1-based start line.",
                },
                "end_line": {
                    "type": "integer",
                    "description": "1-based end line.",
                },
                "recent_count": {
                    "type": "integer",
                    "description": "Recent entry count.",
                    "default": 10,
                },
            },
            "required": ["action"],
        }

    async def execute(
        self,
        action: str,
        content: Optional[str] = None,
        keywords: Optional[str] = None,
        max_results: int = 15,
        match_mode: str = "or",
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        recent_count: int = 10,
        **kwargs,
    ) -> str:
        if action == "write":
            if not content:
                return "write 操作需要提供 content 参数"
            try:
                source = self._channel or "web-chat"
                line_num = self._memory.append_entry(source=source, content=content)
                total = self._memory.get_line_count()
                return f"已写入记忆第 {line_num} 行（共 {total} 条）"
            except Exception as e:
                logger.error(f"Memory write failed: {e}")
                return f"写入记忆失败: {e}"

        elif action == "search":
            if not keywords:
                return "search 操作需要提供 keywords 参数"
            try:
                keyword_list = keywords.strip().split()
                result = self._memory.search(keyword_list, max_results=max_results, match_mode=match_mode)
                stats = self._memory.get_stats()
                return f"记忆库共 {stats['total']} 条\n\n{result}"
            except Exception as e:
                logger.error(f"Memory search failed: {e}")
                return f"搜索记忆失败: {e}"

        elif action == "read":
            try:
                stats = self._memory.get_stats()
                header = f"记忆库共 {stats['total']} 条"
                if stats.get("date_range"):
                    header += f"，时间范围: {stats['date_range']}"
                if start_line is not None:
                    content_result = self._memory.read_lines(start_line, end_line)
                else:
                    content_result = self._memory.get_recent(recent_count)
                return f"{header}\n\n{content_result}"
            except Exception as e:
                logger.error(f"Memory read failed: {e}")
                return f"读取记忆失败: {e}"

        else:
            return f"未知 action: {action}。可选值: write / search / read"
