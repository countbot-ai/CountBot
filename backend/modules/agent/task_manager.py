"""任务取消令牌"""

from typing import Callable

from loguru import logger


class CancellationToken:
    """取消令牌 — 用于协作式任务取消"""

    def __init__(self):
        self._cancelled = False
        self._callbacks: list[Callable] = []

    def cancel(self):
        """标记为已取消并执行回调"""
        if self._cancelled:
            return
        self._cancelled = True
        for cb in self._callbacks:
            try:
                cb()
            except Exception as e:
                logger.error(f"Error in cancellation callback: {e}")

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    def register_callback(self, callback: Callable):
        """注册取消时的回调"""
        self._callbacks.append(callback)
