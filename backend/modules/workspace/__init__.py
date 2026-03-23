"""工作空间管理模块"""

from .manager import WorkspaceManager, workspace_manager
from .seeding import seed_bundled_workspace_resources

__all__ = [
    "workspace_manager",
    "WorkspaceManager",
    "seed_bundled_workspace_resources",
]
