"""工作空间管理模块"""

from .manager import (
    WorkspaceManager,
    get_global_workspace_path,
    resolve_session_workspace,
    validate_session_workspace_path,
    workspace_manager,
)
from .seeding import seed_bundled_workspace_resources

__all__ = [
    "workspace_manager",
    "WorkspaceManager",
    "seed_bundled_workspace_resources",
    "get_global_workspace_path",
    "resolve_session_workspace",
    "validate_session_workspace_path",
]
