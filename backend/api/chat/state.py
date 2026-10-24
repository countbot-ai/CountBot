"""Chat API 的进程级共享状态。

全局 SubagentManager 由 app.py 启动时注入，get_agent_loop、api/tasks.py、
api/tools.py 读写同一个实例。

它通过 global 语句读写，必须集中在这一个模块：分散到多个模块时，每个
模块的 global 只作用于自己的命名空间，会出现多个互不相干的单例。
"""

from typing import Any, Optional

from loguru import logger

# 全局 SubagentManager 实例，由应用启动时注入
_global_subagent_manager: Optional[Any] = None


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

    供 ``get_agent_loop`` 在首次调用时惰性初始化使用：写与读在同一函数内完成，
    避免调用方各自持有 ``global`` 声明。
    """
    global _global_subagent_manager
    if _global_subagent_manager is None:
        _global_subagent_manager = manager
    return _global_subagent_manager
