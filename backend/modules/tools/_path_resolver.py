"""工具路径统一解析：绝对路径原样返回，相对路径按当前工作空间解析。"""

import contextvars
from pathlib import Path
from typing import Optional

# 工具执行期间的会话级工作空间。全局单例仍是渠道/cron 的默认基准，
# 这里只做请求级覆盖，避免会话切换工作空间后 shell cwd 仍指向旧目录。
_current_workspace: contextvars.ContextVar[Optional[Path]] = contextvars.ContextVar(
    "tool_current_workspace",
    default=None,
)


def push_current_workspace(workspace: Optional[Path]) -> contextvars.Token:
    """在工具执行前压入当前会话工作空间。"""
    resolved = workspace.resolve() if workspace is not None else None
    return _current_workspace.set(resolved)


def reset_current_workspace(token: contextvars.Token) -> None:
    """恢复进入工具执行前的工作空间上下文。"""
    _current_workspace.reset(token)


def resolve_path(input_path: str | Path) -> Path:
    """统一路径解析：绝对路径直接返回，相对路径按当前工作空间解析。

    解析优先级：
    1. 工具执行上下文中的会话级工作空间；
    2. `backend.modules.workspace.WorkspaceManager` 全局单例
       （渠道/cron 与设置页热切换仍以它为准）。
    """
    path = Path(input_path)
    if path.is_absolute():
        return path.resolve()

    workspace = _current_workspace.get()
    if workspace is None:
        try:
            from backend.modules.workspace import workspace_manager

            workspace = workspace_manager.workspace_path
        except Exception:
            workspace = Path.cwd()

    return (workspace / path).resolve()
