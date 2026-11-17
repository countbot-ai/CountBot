"""多用户模块：设置、身份解析、权限校验与审计。"""

from backend.modules.multiuser.identity import (
    AuthUser,
    anonymous_admin,
    create_user_session_token,
    get_user_by_id,
    get_user_by_username,
    resolve_session_user,
    revoke_user_sessions,
    user_to_auth_user,
)
from backend.modules.multiuser.settings import (
    APPROVAL_AUTO,
    APPROVAL_MANUAL,
    MODE_ISOLATED,
    MODE_SHARED,
    MultiuserSettings,
    invalidate_cache,
    load_settings,
    save_settings,
)

__all__ = [
    "AuthUser",
    "anonymous_admin",
    "create_user_session_token",
    "get_user_by_id",
    "get_user_by_username",
    "resolve_session_user",
    "revoke_user_sessions",
    "user_to_auth_user",
    "MultiuserSettings",
    "load_settings",
    "save_settings",
    "invalidate_cache",
    "APPROVAL_AUTO",
    "APPROVAL_MANUAL",
    "MODE_SHARED",
    "MODE_ISOLATED",
]
