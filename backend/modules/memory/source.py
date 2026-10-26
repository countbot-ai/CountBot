"""记忆写入来源的解析：取本轮实际渠道，不反推、不兜底，取不到记为 ``unknown``。"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

# 来源无法判定时的落库值。不复用 web-chat，避免把「不知道」伪装成具体渠道。
UNKNOWN_SOURCE = "unknown"

_channel: ContextVar[Optional[str]] = ContextVar("memory_source_channel", default=None)


def set_channel(channel: Optional[str]) -> None:
    """标记当前异步任务的渠道，由工具注册表在每轮开始时调用一次。"""
    _channel.set(channel)


def current_channel() -> Optional[str]:
    """当前异步任务的渠道标识，未标记时为 None。"""
    return _channel.get()


def resolve_source(explicit: Optional[str] = None) -> str:
    """确定一条记忆的写入来源。

    显式传入优先（调用方确知来源时），其次当轮渠道，最后记为 ``unknown``。
    """
    value = (explicit or "").strip()
    if value:
        return value
    return _channel.get() or UNKNOWN_SOURCE
