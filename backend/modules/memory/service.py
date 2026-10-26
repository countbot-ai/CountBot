"""记忆服务：对外的唯一入口。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from loguru import logger

from backend.modules.memory.models import (
    Confidence,
    MemoryEntry,
    MemoryKind,
    generate_key,
    utc_now,
)
from backend.modules.memory.policy import (
    INJECT_TOKEN_BUDGET,
    MAX_RECENT_ENTRIES,
    RECENT_TTL_DAYS,
    apply_lifecycle,
    render_injection,
    select_for_injection,
)
from backend.modules.memory.source import resolve_source
from backend.modules.memory.storage import MemoryStorage


class MemoryDenied(Exception):
    """写入被策略拒绝。"""


@dataclass
class RememberResult:
    """一次写入的结果，供工具层组织回执文案。"""

    entry: MemoryEntry
    replaced_id: Optional[str] = None
    unchanged: bool = False

    def describe(self) -> str:
        if self.unchanged:
            return f"Memory unchanged: [{self.entry.key}] already holds this value."
        if self.replaced_id:
            return (
                f"Memory updated: [{self.entry.key}] replaced entry {self.replaced_id} "
                f"(id={self.entry.id})."
            )
        return f"Memory stored: [{self.entry.key}] (id={self.entry.id})."


class MemoryService:
    """断言式记忆的读写门面。"""

    def __init__(
        self,
        memory_dir: Path,
        *,
        inject_budget: int = INJECT_TOKEN_BUDGET,
        max_recent: int = MAX_RECENT_ENTRIES,
        ttl_days: int = RECENT_TTL_DAYS,
    ):
        self.storage = MemoryStorage(Path(memory_dir))
        self.inject_budget = inject_budget
        self.max_recent = max_recent
        self.ttl_days = ttl_days

    # ---------------------------------------------------------------- 写入

    def remember(
        self,
        key: str,
        value: str,
        *,
        kind: Optional[MemoryKind] = None,
        source: Optional[str] = None,
        source_msg_id: Optional[int] = None,
        confidence: Confidence = Confidence.STATED,
        allow_pinned: bool = False,
    ) -> RememberResult:
        """写入一条断言；同 key 的旧值被取代而不是并列保留。

        ``source`` 缺省时按当轮渠道解析，解析不到记为 unknown——不猜成某个具体渠道。
        """
        source = resolve_source(source)
        memory_key = (key or "").strip() or generate_key(value, source)
        content = " ".join(str(value or "").split())
        if not content:
            raise ValueError("记忆内容不能为空")

        with self.storage.transaction() as entries:
            previous = self._active_by_key(entries, memory_key)
            if previous is not None and previous.kind is MemoryKind.PINNED and not allow_pinned:
                raise MemoryDenied(
                    f"[{memory_key}] is pinned; pinned entries can only be changed from the memory panel"
                )
            target_kind = kind or (previous.kind if previous is not None else MemoryKind.RECENT)
            if confidence is Confidence.INFERRED and target_kind is not MemoryKind.ARCHIVED:
                # 推断内容不具备进入断言层的资格，无论调用方声明了哪一层
                target_kind = MemoryKind.ARCHIVED

            if previous is not None and previous.value == content:
                previous.updated_at = utc_now()
                return RememberResult(entry=previous, unchanged=True)

            entry = MemoryEntry(
                key=memory_key,
                value=content,
                kind=target_kind,
                confidence=confidence,
                source=source,
                source_msg_id=source_msg_id,
                superseded_from=previous.id if previous is not None else None,
            )
            if previous is not None:
                previous.superseded_by = entry.id
                previous.updated_at = utc_now()
            entries.append(entry)
            apply_lifecycle(entries, max_recent=self.max_recent, ttl_days=self.ttl_days)

        logger.info(f"记忆写入 | key={memory_key} | kind={target_kind.value} | 来源={source}")
        return RememberResult(entry=entry, replaced_id=previous.id if previous is not None else None)

    def patch(self, entry_id: str, value: str, *, allow_pinned: bool = False) -> MemoryEntry:
        """改写指定条目的值，旧版本保留在取代链上。"""
        with self.storage.transaction() as entries:
            target = self._require_entry(entries, entry_id)
            if target.kind is MemoryKind.PINNED and not allow_pinned:
                raise MemoryDenied(
                    f"{entry_id} is pinned; pinned entries can only be changed from the memory panel"
                )
            content = " ".join(str(value or "").split())
            if not content:
                raise ValueError("记忆内容不能为空")
            replaced = MemoryEntry(
                key=target.key,
                value=content,
                kind=target.kind,
                confidence=target.confidence,
                source=target.source,
                source_msg_id=target.source_msg_id,
                superseded_from=target.id,
            )
            target.superseded_by = replaced.id
            target.updated_at = utc_now()
            entries.append(replaced)
        logger.info(f"记忆改写 | id={entry_id} | key={replaced.key}")
        return replaced

    def forget(self, entry_id: str, *, allow_pinned: bool = False) -> bool:
        """软删除条目。

        删除只写 ``deleted_at``，行本身保留：误删后用户仍可找回，这是「不物理删除」
        约束的唯一实现点。
        """
        with self.storage.transaction() as entries:
            target = self._find(entries, entry_id)
            if target is None or target.deleted_at:
                return False
            if target.kind is MemoryKind.PINNED and not allow_pinned:
                raise MemoryDenied(
                    f"{entry_id} is pinned; pinned entries can only be removed from the memory panel"
                )
            target.deleted_at = utc_now()
        logger.info(f"记忆软删除 | id={entry_id}")
        return True

    def restore(self, entry_id: str) -> bool:
        with self.storage.transaction() as entries:
            target = self._find(entries, entry_id)
            if target is None or not target.deleted_at:
                return False
            target.deleted_at = None
        logger.info(f"记忆恢复 | id={entry_id}")
        return True

    def set_pinned(self, entry_id: str, pinned: bool) -> Optional[MemoryEntry]:
        """调整条目所在的层。

        推断类内容只在冷存档里有位置：置顶会被拒绝，取消置顶回到 archived。放进
        recent 会让无法验证的内容与显式声明混在同一层展示，看起来像已确认的事实。
        """
        with self.storage.transaction() as entries:
            target = self._find(entries, entry_id)
            if target is None:
                return None
            if target.confidence is Confidence.INFERRED:
                if pinned:
                    raise MemoryDenied(
                        "inferred entries cannot be pinned; restate the fact so it is recorded as stated"
                    )
                target.kind = MemoryKind.ARCHIVED
                target.archived_at = target.archived_at or utc_now()
            elif pinned:
                target.kind = MemoryKind.PINNED
            else:
                target.kind = MemoryKind.RECENT
                target.archived_at = None
            target.updated_at = utc_now()
        return target

    def update_layer(
        self,
        entry_id: str,
        *,
        kind: Optional[MemoryKind] = None,
        confidence: Optional[Confidence] = None,
    ) -> Optional[MemoryEntry]:
        """调整条目的层与可信度，不改变内容。

        「确认这条推断内容有效」需要独立入口：内容对、只是出处不可靠，重写值反而会
        丢掉原文；而 set_pinned 只处理层，无法把 inferred 变成 stated。
        """
        with self.storage.transaction() as entries:
            target = self._find(entries, entry_id)
            if target is None:
                return None
            if confidence is not None:
                target.confidence = confidence
            if kind is not None:
                target.kind = kind
                target.archived_at = utc_now() if kind is MemoryKind.ARCHIVED else None
            target.updated_at = utc_now()
        return target

    # ---------------------------------------------------------------- 读取

    def recall(
        self,
        query: Optional[str] = None,
        *,
        key: Optional[str] = None,
        kind: Optional[MemoryKind] = None,
        limit: int = 12,
    ) -> List[MemoryEntry]:
        """按关键词或 key 检索条目。

        检索覆盖冷存档：被降级条目仍可能有用，只是不再占用上下文预算。命中累加使用
        计数，LRU 降级依赖该信号。
        """
        with self.storage.transaction() as entries:
            candidates = [entry for entry in entries if entry.is_active]
            if key:
                candidates = [entry for entry in candidates if entry.key == key]
            if kind is not None:
                candidates = [entry for entry in candidates if entry.kind is kind]
            if query:
                terms = [term for term in str(query).lower().split() if term]
                candidates = [
                    entry
                    for entry in candidates
                    if all(term in f"{entry.key} {entry.value}".lower() for term in terms)
                ]
            candidates.sort(key=lambda item: (item.hits, item.last_hit_at or item.updated_at), reverse=True)
            selected = candidates[: max(1, limit)]
            for entry in selected:
                entry.mark_hit()
        return selected

    def list_entries(
        self,
        *,
        kind: Optional[MemoryKind] = None,
        limit: int = 50,
        include_inactive: bool = False,
    ) -> List[MemoryEntry]:
        entries = self.storage.load()
        visible = [
            entry
            for entry in entries
            if (include_inactive or entry.is_active) and (kind is None or entry.kind is kind)
        ]
        visible.sort(key=lambda item: item.updated_at, reverse=True)
        return visible[: max(1, limit)]

    def context_block(self) -> str:
        """注入上下文用的正文。

        注入不计命中：若每轮构建提示词都累加计数，所有可注入条目的计数将同步增长，
        LRU 失去区分能力。
        """
        entries = self.storage.load()
        return render_injection(select_for_injection(entries, self.inject_budget))

    # ------------------------------------------------------------ 旧接口兼容

    def append_entry(
        self,
        source: Optional[str],
        content: str,
        *,
        confidence: Confidence = Confidence.STATED,
        kind: Optional[MemoryKind] = None,
    ) -> int:
        """兼容旧调用方的追加式写入。

        key 由内容与来源派生，故同来源的相同内容重复追加不会产生第二份条目；旧的
        「每轮追加一行」正是记忆无限膨胀的来源。``source`` 允许为 None，此时按当轮
        渠道解析。
        """
        resolved = resolve_source(source)
        self.remember(
            generate_key(content, resolved),
            content,
            source=resolved,
            confidence=confidence,
            kind=kind,
        )
        return len(self.storage.load())

    def read_all(self) -> str:
        return self.storage.read_markdown()

    def write_all(self, content: str) -> None:
        """按 markdown 视图整体替换断言层。

        逐 key 比对而非清空重写：未变条目保留原 id 与命中统计，变化条目沿取代链新增
        一版，视图中消失的条目降级进冷存档；反复保存同一内容不产生重复条目。
        """
        parsed = self.storage.parse_markdown(content)
        # 视图中的冷存档仅作展示，不参与断言层替换，否则一次保存会把归档条目整体
        # 「复活」为有效断言。
        parsed = [item for item in parsed if item.kind is not MemoryKind.ARCHIVED]
        with self.storage.transaction() as entries:
            live = [entry for entry in entries if entry.kind is not MemoryKind.ARCHIVED and entry.is_active]
            by_key = {entry.key: entry for entry in live}
            kept: set = set()
            for item in parsed:
                existing = by_key.get(item.key)
                if existing is None:
                    entries.append(item)
                    continue
                kept.add(existing.id)
                if existing.value != item.value:
                    existing.superseded_by = item.id
                    existing.updated_at = utc_now()
                    entries.append(item)
            for entry in live:
                if entry.id not in kept:
                    entry.kind = MemoryKind.ARCHIVED
                    entry.archived_at = utc_now()
        logger.info(f"记忆整体替换 | 断言层条目={len(parsed)}")

    def search(self, keywords: Sequence[str], max_results: int = 15, match_mode: str = "or") -> str:
        """兼容旧搜索接口，返回带 id 的纯文本结果。"""
        terms = [str(term).strip().lower() for term in keywords if str(term).strip()]
        entries = self.storage.load()
        active = [entry for entry in entries if entry.is_active]
        if not terms:
            return "请提供搜索关键词"

        def matches(entry: MemoryEntry) -> bool:
            haystack = f"{entry.key} {entry.value}".lower()
            return all(term in haystack for term in terms) if match_mode == "and" else any(
                term in haystack for term in terms
            )

        hits = [entry for entry in active if matches(entry)]
        if not hits:
            mode_text = "全部" if match_mode == "and" else "任意"
            return f"未找到包含 {mode_text} 关键词 {', '.join(terms)} 的记忆"
        hits.sort(key=lambda item: (item.hits, item.updated_at), reverse=True)
        if len(hits) > max_results:
            total = len(hits)
            hits = hits[:max_results]
            tail = f"... 共 {total} 条匹配，仅显示前 {max_results} 条"
        else:
            tail = ""
        lines = [f"[{entry.id}] [{entry.key}] {entry.value} ({entry.updated_at[:10]}, {entry.source})" for entry in hits]
        if tail:
            lines.append(tail)
        return "\n".join(lines)

    def read_lines(self, start: int, end: Optional[int] = None) -> str:
        entries = self._ordered_active()
        if not entries:
            return "记忆为空"
        stop = end if end is not None else start
        start = max(1, min(start, len(entries)))
        stop = max(start, min(stop, len(entries)))
        return "\n".join(
            f"[{index}] [{entries[index - 1].key}] {entries[index - 1].value}"
            for index in range(start, stop + 1)
        )

    def get_recent(self, count: int = 10) -> str:
        entries = self._ordered_active()[: max(1, count)]
        if not entries:
            return "记忆为空"
        return "\n".join(f"[{index}] [{entry.key}] {entry.value}" for index, entry in enumerate(entries, 1))

    def get_line_count(self) -> int:
        return len(self._ordered_active())

    def delete_lines(self, line_numbers: Sequence[int]) -> int:
        """按行号软删除，行序与 ``read_lines`` 一致。"""
        ordered = self._ordered_active()
        targets = [ordered[index - 1] for index in line_numbers if 1 <= index <= len(ordered)]
        deleted = 0
        for entry in targets:
            if self.forget(entry.id, allow_pinned=True):
                deleted += 1
        return deleted

    def stats(self) -> Dict[str, object]:
        entries = self.storage.load()
        active = [entry for entry in entries if entry.is_active]
        sources: Dict[str, int] = {}
        for entry in active:
            sources[entry.source] = sources.get(entry.source, 0) + 1
        dates = sorted(entry.updated_at[:10] for entry in active)
        return {
            "total": len(active),
            "sources": sources,
            "date_range": f"{dates[0]} ~ {dates[-1]}" if dates else "",
            "layers": {
                "pinned": sum(1 for entry in active if entry.kind is MemoryKind.PINNED),
                "recent": sum(1 for entry in active if entry.kind is MemoryKind.RECENT),
                "archived": sum(1 for entry in active if entry.kind is MemoryKind.ARCHIVED),
            },
        }

    # ---------------------------------------------------------------- 内部

    def _ordered_active(self) -> List[MemoryEntry]:
        entries = [entry for entry in self.storage.load() if entry.is_active]
        entries.sort(key=lambda item: item.updated_at, reverse=True)
        return entries

    @staticmethod
    def _active_by_key(entries: Iterable[MemoryEntry], key: str) -> Optional[MemoryEntry]:
        for entry in entries:
            if entry.key == key and entry.is_active:
                return entry
        return None

    @staticmethod
    def _find(entries: Iterable[MemoryEntry], entry_id: str) -> Optional[MemoryEntry]:
        for entry in entries:
            if entry.id == entry_id:
                return entry
        return None

    def _require_entry(self, entries: Iterable[MemoryEntry], entry_id: str) -> MemoryEntry:
        target = self._find(entries, entry_id)
        if target is None or not target.is_active:
            raise ValueError(f"memory entry {entry_id} not found or already superseded")
        return target
