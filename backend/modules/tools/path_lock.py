"""文件写入串行化。

同一文件的并发写入会互相覆盖：读-改-写之间后写者基于旧内容计算，
先写者的结果被丢弃。主循环与子代理的工具注册表相互独立，同一文件可能
被同时写入，因此按路径加锁；不同路径之间互不阻塞。
"""

import asyncio
from pathlib import Path
from typing import Dict, Optional


class PathLockRegistry:
    """按路径分配异步锁，同一路径的操作串行执行。"""

    def __init__(self) -> None:
        self._locks: Dict[str, asyncio.Lock] = {}
        self._waiters: Dict[str, int] = {}
        # key -> 持有者任务对象，用于识别同任务重入（会自我死锁）
        self._holders: Dict[str, object] = {}

    @staticmethod
    def _key(path: Path) -> str:
        """生成锁键。

        使用 resolve(strict=False) 而非 resolve()：目标文件可能尚不存在，
        严格解析会抛错；非严格模式仍能归一化已存在的父目录与符号链接。
        """
        try:
            return str(path.resolve(strict=False))
        except OSError:
            return str(path)
        except Exception:
            # 锁键生成不得影响调用方语义：非常规 Path 实现（代理对象、测试替身）
            # 退化为字符串表示，仍能保证同一对象串行。
            return str(path)

    def acquire(self, path: Path) -> asyncio.Lock:
        """取得该路径的锁（不等待），返回锁对象供调用方 await。"""
        key = self._key(path)
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
        self._waiters[key] = self._waiters.get(key, 0) + 1
        return lock

    def mark_holder(self, path: Path) -> None:
        """登记当前任务为持有者。"""
        try:
            self._holders[self._key(path)] = asyncio.current_task()
        except RuntimeError:
            # 不在事件循环内（极少见），跳过重入检测
            pass

    def clear_holder(self, path: Path) -> None:
        """清除持有者登记。"""
        self._holders.pop(self._key(path), None)

    def held_by_current_task(self, path: Path) -> bool:
        """该路径是否正被当前任务持有。"""
        try:
            current = asyncio.current_task()
        except RuntimeError:
            return False
        return current is not None and self._holders.get(self._key(path)) is current

    def release(self, path: Path) -> None:
        """归还引用计数，无等待者时回收锁对象。"""
        key = self._key(path)
        remaining = self._waiters.get(key, 1) - 1
        if remaining > 0:
            self._waiters[key] = remaining
            return
        self._waiters.pop(key, None)
        self._holders.pop(key, None)
        lock = self._locks.get(key)
        if lock is not None and not lock.locked():
            self._locks.pop(key, None)


_registry: Optional[PathLockRegistry] = None


def get_path_lock_registry() -> PathLockRegistry:
    """获取进程级路径锁注册表。

    必须是进程级单例：每个工具实例各持一份注册表起不到互斥作用。
    """
    global _registry
    if _registry is None:
        _registry = PathLockRegistry()
    return _registry


class path_write_lock:
    """路径写入锁的异步上下文管理器。"""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._registry = get_path_lock_registry()
        self._lock: Optional[asyncio.Lock] = None

    async def __aenter__(self) -> "path_write_lock":
        self._lock = self._registry.acquire(self._path)

        # asyncio.Lock 不可重入，同任务对同一路径嵌套获取会永久挂起。
        # 直接抛错，比请求卡死好排查得多。
        if self._lock.locked() and self._registry.held_by_current_task(self._path):
            self._registry.release(self._path)
            raise RuntimeError(
                f"path_write_lock is not reentrant: {self._path} is already "
                "held by the current task; avoid nesting locks on the same path"
            )

        try:
            await self._lock.acquire()
        except asyncio.CancelledError:
            self._registry.release(self._path)
            raise
        self._registry.mark_holder(self._path)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        if self._lock is not None and self._lock.locked():
            self._lock.release()
        self._registry.clear_holder(self._path)
        self._registry.release(self._path)
        return False
