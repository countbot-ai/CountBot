"""Chat API 的进程级共享状态，集中管理全局单例。"""

from typing import Any, Optional

from loguru import logger

_global_subagent_manager: Optional[Any] = None
# 会话级工作空间各自持有 SubagentManager，避免切换目录时覆盖全局实例
_workspace_subagent_managers: dict[str, Any] = {}
# 多用户：每个普通用户一个 SubagentManager，任务列表按实例隔离
_user_subagent_managers: dict[str, Any] = {}


def register_user_subagent_manager(user_id: str, manager) -> None:
    """登记某用户的 SubagentManager（由 UserRuntimeManager 调用）。"""
    if not user_id:
        return
    _user_subagent_managers[user_id] = manager


def unregister_user_subagent_manager(user_id: str) -> None:
    if not user_id:
        return
    _user_subagent_managers.pop(user_id, None)


def get_user_subagent_manager(user_id: Optional[str]):
    if not user_id:
        return None
    return _user_subagent_managers.get(user_id)


def set_global_subagent_manager(manager) -> None:
    """设置全局 SubagentManager 实例。"""
    global _global_subagent_manager
    _global_subagent_manager = manager
    logger.info("Global SubagentManager set")


def get_global_subagent_manager():
    """获取全局 SubagentManager 实例。"""
    return _global_subagent_manager


def ensure_global_subagent_manager(manager) -> Any:
    """若尚未设置则写入并返回当前实例，供 ``get_agent_loop`` 惰性初始化。"""
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
