"""工作空间管理模块"""

from .manager import (
    WorkspaceManager,
    archive_user_workspace,
    ensure_user_workspace,
    get_effective_user_root,
    get_global_workspace_path,
    get_user_workspace_root,
    get_users_root,
    is_path_within_user_workspace,
    resolve_session_workspace,
    resolve_user_workspace,
    validate_session_workspace_path,
    workspace_manager,
)
from .seeding import (
    bundled_skill_copy_names,
    bundled_skills_dir,
    builtin_skill_manifest_path,
    builtin_skill_names,
    seed_bundled_workspace_resources,
)

__all__ = [
    "workspace_manager",
    "WorkspaceManager",
    "seed_bundled_workspace_resources",
    "bundled_skill_copy_names",
    "bundled_skills_dir",
    "builtin_skill_manifest_path",
    "builtin_skill_names",
    "get_global_workspace_path",
    "get_users_root",
    "get_effective_user_root",
    "get_user_workspace_root",
    "ensure_user_workspace",
    "archive_user_workspace",
    "resolve_user_workspace",
    "is_path_within_user_workspace",
    "resolve_session_workspace",
    "validate_session_workspace_path",
]
