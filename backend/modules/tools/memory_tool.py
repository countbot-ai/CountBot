"""记忆工具：只暴露断言式操作（``remember`` / ``patch`` / ``forget``）。"""

from typing import Any, Dict, List, Optional

from loguru import logger

from backend.modules.memory import (
    Confidence,
    MemoryDenied,
    MemoryKind,
    MemoryService,
)
from backend.modules.memory import source as memory_source
from backend.modules.memory.source import resolve_source
from backend.modules.tools.base import Tool
from backend.modules.tools.execution import ErrorCategory, RetrySafety, SideEffectState, ToolResult

_KIND_ALIASES = {
    "pinned": MemoryKind.PINNED,
    "recent": MemoryKind.RECENT,
    "archived": MemoryKind.ARCHIVED,
}


def _parse_kind(raw: Optional[str]) -> Optional[MemoryKind]:
    if not raw:
        return None
    return _KIND_ALIASES.get(str(raw).strip().lower())


def _format_entry(entry) -> str:
    return (
        f"[{entry.id}] [{entry.key}] {entry.value} "
        f"({entry.updated_at[:10]}, {entry.kind.value}, {entry.source})"
    )


def _denied_message(exc: MemoryDenied) -> str:
    return f"Rejected: {exc}. Ask the user to change it from the memory panel if it must change."


class MemoryTool(Tool):
    """统一记忆工具，通过 action 路由到具体的断言操作。"""

    def __init__(self, memory_store: MemoryService):
        self._memory = memory_store
        # 来源以当轮渠道上下文为准（见 backend.modules.memory.source）；该属性只服务
        # 直接构造工具、不经注册表的调用方（脚本与测试）
        self._channel: Optional[str] = None

    def set_channel(self, channel: Optional[str]) -> None:
        """设置当前渠道，用作写入条目的来源。"""
        self._channel = channel

    def _source(self) -> str:
        """解析本条写入的来源：当轮渠道优先，其次实例值，都没有则 unknown。"""
        return memory_source.current_channel() or resolve_source(self._channel)

    @property
    def name(self) -> str:
        return "memory"

    @property
    def description(self) -> str:
        return "Long-term memory: `remember`, `recall`, `patch`, `forget`, `list`."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Memory action.",
                    "enum": ["remember", "recall", "patch", "forget", "list"],
                },
                "key": {
                    "type": "string",
                    "description": "Stable subject key, e.g. `cache.backend`. Required for `remember`.",
                },
                "value": {
                    "type": "string",
                    "description": "Assertion text. Required for `remember` and `patch`.",
                },
                "entry_id": {
                    "type": "string",
                    "description": "Target entry id from `recall`/`list`. Required for `patch` and `forget`.",
                },
                "query": {
                    "type": "string",
                    "description": "Space-separated keywords; every term must match. Omit to browse by recency.",
                },
                "kind": {
                    "type": "string",
                    "description": (
                        "Layer filter for `list`. For `remember`, `pinned` is not accepted: "
                        "pinning is a user decision, new entries land in `recent`."
                    ),
                    "enum": ["pinned", "recent", "archived"],
                },
                "limit": {
                    "type": "integer",
                    "description": "Max entries to return.",
                    "default": 12,
                },
            },
            "required": ["action"],
        }

    async def execute(
        self,
        action: str,
        key: Optional[str] = None,
        value: Optional[str] = None,
        entry_id: Optional[str] = None,
        query: Optional[str] = None,
        kind: Optional[str] = None,
        limit: int = 12,
        **kwargs,
    ) -> str:
        try:
            return self._dispatch(action, key, value, entry_id, query, kind, limit)
        except MemoryDenied as exc:
            return _denied_message(exc)
        except Exception as exc:
            logger.error(f"Memory tool failed: {exc}")
            return f"Memory {action} failed: {exc}"

    async def execute_outcome(
        self,
        action: str,
        key: Optional[str] = None,
        value: Optional[str] = None,
        entry_id: Optional[str] = None,
        query: Optional[str] = None,
        kind: Optional[str] = None,
        limit: int = 12,
        **kwargs,
    ) -> ToolResult:
        mutating = action in ("remember", "patch", "forget")
        retry_safety = RetrySafety.UNSAFE if mutating else RetrySafety.SAFE
        try:
            text = self._dispatch(action, key, value, entry_id, query, kind, limit)
        except MemoryDenied as exc:
            return ToolResult.failure(
                ErrorCategory.VALIDATION,
                _denied_message(exc),
                retry_safety=RetrySafety.UNSAFE,
                side_effect_state=SideEffectState.NOT_ATTEMPTED,
            )
        except ValueError as exc:
            return ToolResult.failure(
                ErrorCategory.VALIDATION,
                str(exc),
                retry_safety=retry_safety,
                side_effect_state=SideEffectState.NOT_ATTEMPTED,
            )
        except Exception as exc:
            logger.error(f"Memory tool failed: {exc}")
            return ToolResult.failure(
                ErrorCategory.EXECUTION,
                f"Memory {action} failed: {exc}",
                retry_safety=retry_safety,
                side_effect_state=SideEffectState.UNKNOWN if mutating else SideEffectState.NOT_APPLICABLE,
            )
        return ToolResult.success(
            text,
            retry_safety=retry_safety,
            side_effect_state=SideEffectState.COMMITTED if mutating else SideEffectState.NOT_APPLICABLE,
        )

    # ---------------------------------------------------------------- 内部

    def _dispatch(
        self,
        action: str,
        key: Optional[str],
        value: Optional[str],
        entry_id: Optional[str],
        query: Optional[str],
        kind: Optional[str],
        limit: int,
    ) -> str:
        source = self._source()

        if action == "remember":
            if not value:
                raise ValueError("`remember` requires `value`")
            resolved_kind = _parse_kind(kind)
            downgraded = False
            if resolved_kind is MemoryKind.PINNED:
                # 置顶只由人工产生：模型自封的 pinned 会堵死后续一切修正，
                # 因为 pinned 条目对模型侧的 patch/forget 一律拒绝
                resolved_kind = MemoryKind.RECENT
                downgraded = True
            result = self._memory.remember(
                key or "",
                value,
                kind=resolved_kind,
                source=source,
                confidence=Confidence.STATED,
            )
            if downgraded:
                return result.describe() + " Stored as recent (pinned is set by the user)."
            return result.describe()

        if action == "patch":
            if not entry_id:
                raise ValueError("`patch` requires `entry_id`")
            if not value:
                raise ValueError("`patch` requires `value`")
            entry = self._memory.patch(entry_id, value)
            return (
                f"Memory patched: [{entry.key}] now holds the new text (id={entry.id}). "
                "The previous version is kept for rollback."
            )

        if action == "forget":
            if not entry_id:
                raise ValueError("`forget` requires `entry_id`")
            removed = self._memory.forget(entry_id)
            if not removed:
                return f"No active memory entry with id {entry_id}."
            return f"Memory entry {entry_id} removed (soft delete; it can be restored)."

        if action == "recall":
            entries = self._memory.recall(query, key=key, kind=_parse_kind(kind), limit=limit)
            return self._render(entries, empty="No memory entry matched.")

        if action == "list":
            entries = self._memory.list_entries(kind=_parse_kind(kind), limit=limit)
            return self._render(entries, empty="Memory is empty.")

        raise ValueError(f"Unknown action '{action}'. Use remember / recall / patch / forget / list.")

    @staticmethod
    def _render(entries: List[Any], *, empty: str) -> str:
        if not entries:
            return empty
        return "\n".join([f"{len(entries)} memory entries.", *(_format_entry(item) for item in entries)])


# ==============================================================================
# 兼容类：旧注册表按工具名查找时仍需存在，实际行为路由到同一套服务
# ==============================================================================


class MemoryWriteTool(Tool):
    """兼容旧工具名 ``memory_write``。"""

    def __init__(self, memory_store: MemoryService):
        self._memory = memory_store
        self._channel: Optional[str] = None

    def set_channel(self, channel: Optional[str]) -> None:
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
            "properties": {"content": {"type": "string", "description": "Memory text."}},
            "required": ["content"],
        }

    async def execute(self, content: str, **kwargs) -> str:
        try:
            result = self._memory.remember("", content, source=resolve_source(self._channel))
            return result.describe()
        except MemoryDenied as exc:
            return _denied_message(exc)
        except Exception as exc:
            logger.error(f"Memory write failed: {exc}")
            return f"Memory write failed: {exc}"

    async def execute_outcome(self, content: str, **kwargs) -> ToolResult:
        text = await self.execute(content, **kwargs)
        return ToolResult.success(
            text,
            retry_safety=RetrySafety.UNSAFE,
            side_effect_state=SideEffectState.COMMITTED,
        )


class MemorySearchTool(Tool):
    """兼容旧工具名 ``memory_search``。"""

    def __init__(self, memory_store: MemoryService):
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
                "keywords": {"type": "string", "description": "Search keywords."},
                "max_results": {"type": "integer", "description": "Max results.", "default": 15},
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
            result = self._memory.search(keywords.strip().split(), max_results=max_results, match_mode=match_mode)
            return f"{self._memory.get_line_count()} memory entries.\n\n{result}"
        except Exception as exc:
            logger.error(f"Memory search failed: {exc}")
            return f"Memory search failed: {exc}"

    async def execute_outcome(
        self,
        keywords: str,
        max_results: int = 15,
        match_mode: str = "or",
        **kwargs,
    ) -> ToolResult:
        text = await self.execute(keywords, max_results=max_results, match_mode=match_mode, **kwargs)
        return ToolResult.success(
            text,
            retry_safety=RetrySafety.SAFE,
            side_effect_state=SideEffectState.NOT_APPLICABLE,
        )


class MemoryReadTool(Tool):
    """兼容旧工具名 ``memory_read``。"""

    def __init__(self, memory_store: MemoryService):
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
                "start_line": {"type": "integer", "description": "1-based start line."},
                "end_line": {"type": "integer", "description": "1-based end line."},
                "recent_count": {"type": "integer", "description": "Recent entry count.", "default": 10},
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
            stats = self._memory.stats()
            header = f"{stats['total']} memory entries"
            if stats.get("date_range"):
                header += f", range: {stats['date_range']}"
            content = (
                self._memory.read_lines(start_line, end_line)
                if start_line is not None
                else self._memory.get_recent(recent_count)
            )
            return f"{header}\n\n{content}"
        except Exception as exc:
            logger.error(f"Memory read failed: {exc}")
            return f"Memory read failed: {exc}"

    async def execute_outcome(
        self,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        recent_count: int = 10,
        **kwargs,
    ) -> ToolResult:
        text = await self.execute(start_line, end_line, recent_count, **kwargs)
        return ToolResult.success(
            text,
            retry_safety=RetrySafety.SAFE,
            side_effect_state=SideEffectState.NOT_APPLICABLE,
        )
