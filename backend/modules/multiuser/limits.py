"""并发准入控制：全局同时生成不超过 10 个，每用户 1 个。

使用同步计数器：检查与占用之间没有 ``await``，在事件循环中保持原子性。
"""

from __future__ import annotations

import os
from typing import Dict, Optional

from fastapi import HTTPException, status


GLOBAL_MAX_CONCURRENT = int(os.getenv("COUNTBOT_MAX_CONCURRENT_TURNS", "10"))


class ConcurrencyLimit:
    def __init__(self, global_limit: int = GLOBAL_MAX_CONCURRENT) -> None:
        self._limit = max(1, global_limit)
        self._active_global = 0
        self._active_user: Dict[str, int] = {}

    def try_acquire(self, owner_id: Optional[str]) -> None:
        """占用一个名额；超限直接抛 429，不排队。"""
        if owner_id and self._active_user.get(owner_id, 0) >= 1:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={"detail": "你有正在生成的对话，请等待完成", "code": "USER_BUSY"},
            )
        if self._active_global >= self._limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={"detail": "当前并发已满，请稍后重试", "code": "CONCURRENCY_LIMIT"},
            )
        self._active_global += 1
        if owner_id:
            self._active_user[owner_id] = self._active_user.get(owner_id, 0) + 1

    def release(self, owner_id: Optional[str]) -> None:
        self._active_global = max(0, self._active_global - 1)
        if owner_id and owner_id in self._active_user:
            remaining = self._active_user[owner_id] - 1
            if remaining > 0:
                self._active_user[owner_id] = remaining
            else:
                self._active_user.pop(owner_id, None)

    def stats(self) -> Dict[str, int]:
        return {"active": self._active_global, "limit": self._limit}


turn_limit = ConcurrencyLimit()
