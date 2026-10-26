"""记忆条目的数据模型：同 key 的新值覆盖旧值并保留取代链。"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from backend.modules.memory.source import UNKNOWN_SOURCE


class MemoryKind(str, Enum):
    """条目所处的生命周期层。"""

    # 永不淘汰，只允许人工改动；注入上下文的主体
    PINNED = "pinned"
    # 常规断言，按 TTL 与 LRU 降级
    RECENT = "recent"
    # 冷存档，只可检索，不注入
    ARCHIVED = "archived"


class Confidence(str, Enum):
    """条目来源的可信度。

    ``stated`` 由用户或模型显式声明；``inferred`` 由对话摘要推断，无法验证。
    """

    STATED = "stated"
    INFERRED = "inferred"


def utc_now() -> str:
    """当前时间，统一用秒级 UTC ISO 字符串，便于直接比较与排序。"""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def generate_key(value: str, source: str) -> str:
    """为未显式给出 key 的条目生成稳定键。

    以内容与来源的摘要作键，使同来源的相同内容重复写入时自然合并，而非堆积多条
    等价断言。
    """
    digest = hashlib.sha1(f"{source}\n{value}".encode("utf-8")).hexdigest()[:12]
    return f"auto.{digest}"


@dataclass
class MemoryEntry:
    """一条记忆断言。"""

    key: str
    value: str
    kind: MemoryKind = MemoryKind.RECENT
    confidence: Confidence = Confidence.STATED
    # 写入来源；缺省值必须是 unknown 而不是某个具体渠道，否则无从判定出处的条目
    # 会伪装成网页来源
    source: str = UNKNOWN_SOURCE
    source_msg_id: Optional[int] = None
    id: str = field(default_factory=lambda: f"m_{uuid.uuid4().hex[:10]}")
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    last_hit_at: Optional[str] = None
    hits: int = 0
    # 被哪条条目取代；有值表示本条已失效，但内容保留以便回溯与回滚
    superseded_by: Optional[str] = None
    # 本条覆盖掉的上一版条目 id，删除本条即可回滚
    superseded_from: Optional[str] = None
    archived_at: Optional[str] = None
    deleted_at: Optional[str] = None

    @property
    def is_active(self) -> bool:
        """是否仍代表当前有效事实。"""
        return self.superseded_by is None and self.deleted_at is None

    @property
    def is_injectable(self) -> bool:
        """是否有资格进入上下文注入。"""
        return (
            self.is_active
            and self.kind in (MemoryKind.PINNED, MemoryKind.RECENT)
            and self.confidence is Confidence.STATED
        )

    def mark_hit(self) -> None:
        self.hits += 1
        self.last_hit_at = utc_now()

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "id": self.id,
            "key": self.key,
            "value": self.value,
            "kind": self.kind.value,
            "confidence": self.confidence.value,
            "source": self.source,
            "source_msg_id": self.source_msg_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_hit_at": self.last_hit_at,
            "hits": self.hits,
            "superseded_by": self.superseded_by,
            "superseded_from": self.superseded_from,
            "archived_at": self.archived_at,
            "deleted_at": self.deleted_at,
        }
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "MemoryEntry":
        """从落盘数据还原条目。

        未知字段直接丢弃而不报错：旧版本写入的行必须仍可读入，否则一次字段调整即令
        整个记忆文件不可用。
        """
        return cls(
            id=str(payload.get("id") or f"m_{uuid.uuid4().hex[:10]}"),
            key=str(payload.get("key") or ""),
            value=str(payload.get("value") or ""),
            kind=_coerce_enum(MemoryKind, payload.get("kind"), MemoryKind.RECENT),
            confidence=_coerce_enum(Confidence, payload.get("confidence"), Confidence.STATED),
            source=str(payload.get("source") or UNKNOWN_SOURCE),
            source_msg_id=_coerce_int(payload.get("source_msg_id")),
            created_at=str(payload.get("created_at") or utc_now()),
            updated_at=str(payload.get("updated_at") or utc_now()),
            last_hit_at=_coerce_str(payload.get("last_hit_at")),
            hits=_coerce_int(payload.get("hits")) or 0,
            superseded_by=_coerce_str(payload.get("superseded_by")),
            superseded_from=_coerce_str(payload.get("superseded_from")),
            archived_at=_coerce_str(payload.get("archived_at")),
            deleted_at=_coerce_str(payload.get("deleted_at")),
        )

    def render_line(self) -> str:
        """渲染为 markdown 视图中的一行。

        该格式同时是人工编辑的输入格式：``write_all`` 按同样规则回解析，
        因此视图与存储不会因为一次手工编辑而分叉。
        """
        return f"- [{self.key}] {self.value} | {self.updated_at[:10]} | {self.source}"


def _coerce_enum(enum_cls, value: Any, default):
    try:
        return enum_cls(str(value))
    except (ValueError, TypeError):
        return default


def _coerce_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_str(value: Any) -> Optional[str]:
    if value is None or value == "":
        return None
    return str(value)
