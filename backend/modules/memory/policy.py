"""记忆的生命周期与注入选择策略：淘汰与注入均为确定性函数。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional, Sequence

from backend.modules.memory.models import MemoryEntry, MemoryKind, utc_now

# 注入上下文的 token 预算。记忆无需检索即生效，但上下文空间属于对话本身，故设固定
# 上限；超出预算的条目只能经 recall 取回。
INJECT_TOKEN_BUDGET = 300

# recent 层条目上限，超出后按最久未命中降级，避免检索结果被陈旧条目淹没
MAX_RECENT_ENTRIES = 200

# recent 层的闲置保留天数，超期后降级进冷存档
RECENT_TTL_DAYS = 90


def select_for_injection(
    entries: Iterable[MemoryEntry],
    budget_tokens: int = INJECT_TOKEN_BUDGET,
) -> List[MemoryEntry]:
    """挑出进入上下文的条目。

    pinned 优先（明确要求长期生效，缺一条即可能违反用户意图），剩余预算给命中次数
    最多的 recent；同命中次数按更新时间倒序，保证输出确定。
    """
    active = [entry for entry in entries if entry.is_injectable]
    pinned = sorted(
        (entry for entry in active if entry.kind is MemoryKind.PINNED),
        key=lambda item: item.updated_at,
        reverse=True,
    )
    recent = sorted(
        (entry for entry in active if entry.kind is MemoryKind.RECENT),
        key=lambda item: (item.hits, item.last_hit_at or item.updated_at),
        reverse=True,
    )

    selected: List[MemoryEntry] = []
    used = 0
    for entry in [*pinned, *recent]:
        cost = _entry_cost(entry)
        if selected and used + cost > budget_tokens:
            break
        selected.append(entry)
        used += cost
    return selected


def render_injection(entries: Sequence[MemoryEntry]) -> str:
    """把选中的条目渲染成上下文区块正文，空集合返回空串。"""
    if not entries:
        return ""
    return "\n".join(f"- [{entry.key}] {entry.value}" for entry in entries)


def apply_lifecycle(
    entries: List[MemoryEntry],
    *,
    now: Optional[datetime] = None,
    max_recent: int = MAX_RECENT_ENTRIES,
    ttl_days: int = RECENT_TTL_DAYS,
) -> List[MemoryEntry]:
    """就地执行 TTL 与 LRU 降级，返回被降级的条目。

    降级不等于删除：冷存档仍可检索，故本步无损，无需任何「删前确认」交互。
    """
    moment = now or datetime.now(timezone.utc)
    demoted: List[MemoryEntry] = []

    recent = [entry for entry in entries if entry.kind is MemoryKind.RECENT and entry.is_active]
    expired_ids = {entry.id for entry in recent if _is_expired(entry, moment, ttl_days)}
    overflow = _overflow_ids(recent, max_recent, expired_ids)

    for entry in recent:
        if entry.id in expired_ids or entry.id in overflow:
            entry.kind = MemoryKind.ARCHIVED
            entry.archived_at = utc_now()
            demoted.append(entry)
    return demoted


def _overflow_ids(
    recent: Sequence[MemoryEntry],
    max_recent: int,
    already_demoted: set,
) -> set:
    survivors = [entry for entry in recent if entry.id not in already_demoted]
    if len(survivors) <= max_recent:
        return set()
    ordered = sorted(
        survivors,
        key=lambda item: (item.hits, item.last_hit_at or item.updated_at),
    )
    return {entry.id for entry in ordered[: len(survivors) - max_recent]}


def _is_expired(entry: MemoryEntry, now: datetime, ttl_days: int) -> bool:
    reference = entry.last_hit_at or entry.updated_at
    moment = _parse(reference)
    if moment is None:
        return False
    return now - moment > timedelta(days=ttl_days)


def _parse(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _entry_cost(entry: MemoryEntry) -> int:
    """单条条目的 token 成本，按渲染后的文本估算。"""
    from backend.modules.compression.tokens import estimate_tokens

    return estimate_tokens(f"- [{entry.key}] {entry.value}")
