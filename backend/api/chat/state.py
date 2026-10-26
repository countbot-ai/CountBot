"""Chat API 的进程级共享状态：全局 SubagentManager 经 global 集中在本模块，分散会导致多个单例。"""

from typing import Any, Optional

from loguru import logger

_global_subagent_manager: Optional[Any] = None
# 会话级工作空间各自持有 SubagentManager，避免切换目录时覆盖全局实例
_workspace_subagent_managers: dict[str, Any] = {}


def set_global_subagent_manager(manager) -> None:
    """设置全局 SubagentManager 实例。"""
    global _global_subagent_manager
    _global_subagent_manager = manager
    logger.info("Global SubagentManager set")


def get_global_subagent_manager():
    """获取全局 SubagentManager 实例。"""
    return _global_subagent_manager


def ensure_global_subagent_manager(manager) -> Any:
    """若尚未设置则写入并返回当前实例。

    供 ``get_agent_loop`` 惰性初始化：读写同函数完成，避免调用方各自声明 ``global``。
    """
    global _global_subagent_manager
    if _global_subagent_manager is None:
        _global_subagent_manager = manager
    return _global_subagent_manager


def get_or_create_workspace_subagent_manager(workspace_key: str, factory) -> Any:
    """按工作空间缓存 SubagentManager，避免会话级工作空间互相覆盖。"""
    manager = _workspace_subagent_managers.get(workspace_key)
    if manager is None:
        manager = factory()
        _workspace_subagent_managers[workspace_key] = manager
    return manager
