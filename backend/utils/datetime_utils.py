"""日期时间序列化工具。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def to_utc_iso(dt: Optional[datetime]) -> Optional[str]:
    """将 datetime 统一序列化为带时区的 UTC ISO 8601 字符串。"""
    if dt is None:
        return None

    normalized = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    return normalized.isoformat().replace("+00:00", "Z")
